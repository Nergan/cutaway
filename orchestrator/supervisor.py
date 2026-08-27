"""Lifecycle and resource supervision for isolated project workers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ProjectConfig, RuntimeConfig

try:
    import psutil
except ImportError:  # pragma: no cover - deployment installs it; fallback stays usable.
    psutil = None


logger = logging.getLogger(__name__)
SAFE_ENV_KEYS = {
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LANG",
    "NO_PROXY",
    "PATH",
    "PIP_CERT",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "SYSTEMROOT",
    "TZ",
    "WINDIR",
}


class WorkerUnavailable(RuntimeError):
    def __init__(self, message: str, *, retry_after: int = 1):
        super().__init__(message)
        self.retry_after = max(1, retry_after)


@dataclass
class WorkerMetrics:
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    processes: int = 0
    connections: int = 0
    temp_mb: float = 0.0


@dataclass
class WorkerRuntime:
    project: ProjectConfig
    process: asyncio.subprocess.Process | None = None
    status: str = "stopped"
    last_error: str | None = None
    last_request: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    circuit_until: float = 0.0
    restart_times: deque[float] = field(default_factory=deque)
    consecutive_proxy_failures: int = 0
    cpu_over_since: float | None = None
    metrics: WorkerMetrics = field(default_factory=WorkerMetrics)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ProjectSupervisor:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.workers = {
            project.project_id: WorkerRuntime(project=project)
            for project in config.for_phase("run")
        }
        self._monitor_task: asyncio.Task[None] | None = None
        self._closing = False
        self._temp_scan_tick = 0
        self._resource_warning_logged = False

    async def start(self) -> None:
        self._closing = False
        for worker in self.workers.values():
            if worker.project.startup == "eager":
                try:
                    await self.ensure_running(worker.project.project_id)
                except WorkerUnavailable as exc:
                    logger.error("Eager worker %s failed: %s", worker.project.project_id, exc)
        self._monitor_task = asyncio.create_task(self._monitor_loop(), name="project-supervisor")

    async def stop(self) -> None:
        self._closing = True
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        await asyncio.gather(
            *(self._stop_worker(worker, expected=True, reason="hub shutdown") for worker in self.workers.values()),
            return_exceptions=True,
        )

    def _runtime_dir(self, project: ProjectConfig) -> Path:
        base = Path(
            os.getenv(
                "CUTAWAY_RUNTIME_DIR",
                str(Path(tempfile.gettempdir()) / "cutaway-runtime"),
            )
        )
        return base / self.config.profile / project.project_id

    def _venv_python(self, project: ProjectConfig) -> Path | None:
        base = Path(
            os.getenv(
                "CUTAWAY_VENV_ROOT",
                str(self.config.root / ".orchestrator" / "venvs"),
            )
        )
        venv = base / self.config.profile / project.project_id
        candidate = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return candidate if candidate.is_file() else None

    def _worker_env(self, project: ProjectConfig, runtime_dir: Path) -> dict[str, str]:
        env: dict[str, str] = {}
        for key, value in os.environ.items():
            if key in SAFE_ENV_KEYS or key.startswith("LC_"):
                env[key] = value
        for key in project.env_allowlist:
            if key in os.environ:
                env[key] = os.environ[key]
            elif key in project.env_defaults:
                env[key] = project.env_defaults[key]

        home = runtime_dir / "home"
        temp = runtime_dir / "tmp"
        cache = runtime_dir / "cache"
        for directory in (home, temp, cache):
            directory.mkdir(parents=True, exist_ok=True)

        network_hosts = project.network.allowed_hosts
        if project.project_id == "yellow_mirror" and os.getenv("YELLOW_MIRROR_ALLOWED_HOSTS"):
            network_hosts = tuple(
                host.strip()
                for host in os.environ["YELLOW_MIRROR_ALLOWED_HOSTS"].split(",")
                if host.strip()
            )
        env.update(
            {
                "CUTAWAY_PROFILE": self.config.profile,
                "CUTAWAY_ISOLATION": "isolated",
                "CUTAWAY_WORKER_PROJECT": project.project_id,
                "CUTAWAY_PROJECT_NETWORK_HOSTS": ",".join(network_hosts),
                "CUTAWAY_PROJECT_ALLOW_PRIVATE_NETWORK": "1" if project.network.allow_private else "0",
                "CUTAWAY_PROJECT_NETWORK_RPM": str(project.network.requests_per_minute),
                "CUTAWAY_HEAVY_JOBS": str(max(1, min(2, project.limits.max_concurrency))),
                "CUTAWAY_CLOUDINARY_CONCURRENCY": str(
                    max(1, min(2, project.limits.max_concurrency))
                ),
                "HOME": str(home),
                "TMP": str(temp),
                "TEMP": str(temp),
                "TMPDIR": str(temp),
                "XDG_CACHE_HOME": str(cache),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            }
        )
        if not network_hosts:
            env.update(
                {
                    "ALL_PROXY": "http://127.0.0.1:9",
                    "HTTP_PROXY": "http://127.0.0.1:9",
                    "HTTPS_PROXY": "http://127.0.0.1:9",
                    "NO_PROXY": "127.0.0.1,localhost",
                }
            )
        return env

    @staticmethod
    def _limit_child(project: ProjectConfig) -> None:
        if os.name != "posix":
            return
        import resource

        def set_soft_limit(kind: int, desired: int) -> None:
            _, hard = resource.getrlimit(kind)
            maximum = desired if hard == resource.RLIM_INFINITY else min(desired, hard)
            resource.setrlimit(kind, (maximum, hard))

        set_soft_limit(resource.RLIMIT_NOFILE, max(32, project.limits.nofile))
        set_soft_limit(resource.RLIMIT_FSIZE, max(1, project.limits.fsize_mb) * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        with contextlib.suppress(OSError):
            os.nice(5)

    async def ensure_running(self, project_id: str) -> WorkerRuntime:
        worker = self.workers.get(project_id)
        if worker is None:
            raise WorkerUnavailable(f"Project {project_id} is disabled.", retry_after=60)
        worker.last_request = time.monotonic()

        async with worker.lock:
            if self._closing:
                raise WorkerUnavailable("The project supervisor is shutting down.", retry_after=5)
            if worker.process is not None and worker.process.returncode is None:
                return worker

            now = time.monotonic()
            if worker.circuit_until > now:
                worker.status = "circuit_open"
                raise WorkerUnavailable(
                    f"Project {project_id} is temporarily isolated after repeated failures.",
                    retry_after=int(worker.circuit_until - now) + 1,
                )
            if worker.circuit_until:
                worker.circuit_until = 0.0
                worker.restart_times.clear()

            self._trim_restarts(worker, now)
            if len(worker.restart_times) >= worker.project.limits.restart_max:
                worker.circuit_until = now + worker.project.limits.restart_window_seconds
                worker.status = "circuit_open"
                raise WorkerUnavailable(
                    f"Project {project_id} exceeded its restart budget.",
                    retry_after=int(worker.project.limits.restart_window_seconds),
                )

            await self._spawn(worker)
            return worker

    async def _spawn(self, worker: WorkerRuntime) -> None:
        project = worker.project
        runtime_dir = self._runtime_dir(project)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        venv_python = self._venv_python(project)
        require_venv = os.getenv("CUTAWAY_REQUIRE_VENVS", "0") == "1"
        if self.config.dependency_isolation and require_venv and venv_python is None:
            self._register_failure(worker, "isolated virtual environment is missing")
            raise WorkerUnavailable(f"Worker environment for {project.project_id} is missing.", retry_after=30)
        executable = str(venv_python or Path(sys.executable))

        command = [
            executable,
            "-m",
            "uvicorn",
            "orchestrator.worker:create_app",
            "--factory",
            "--host",
            self.config.worker_host,
            "--port",
            str(project.port),
            "--loop",
            "asyncio",
            "--proxy-headers",
            "--forwarded-allow-ips",
            self.config.worker_host,
        ]
        worker.status = "starting"
        worker.last_error = None
        kwargs: dict[str, Any] = {
            "cwd": str(self.config.root),
            "env": self._worker_env(project, runtime_dir),
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
            kwargs["preexec_fn"] = lambda: self._limit_child(project)
        try:
            worker.process = await asyncio.create_subprocess_exec(*command, **kwargs)
            await self._wait_until_ready(worker)
        except Exception as exc:
            await self._stop_worker(worker, expected=False, reason=f"startup failed: {exc}")
            raise WorkerUnavailable(
                f"Project {project.project_id} failed to start.",
                retry_after=max(1, int(project.limits.restart_backoff_seconds)),
            ) from exc

        worker.status = "online"
        worker.started_at = time.time()
        worker.last_request = time.monotonic()
        worker.consecutive_proxy_failures = 0
        logger.info("Project %s started as pid %s", project.project_id, worker.process.pid)

    async def _wait_until_ready(self, worker: WorkerRuntime) -> None:
        deadline = time.monotonic() + worker.project.limits.startup_timeout_seconds
        while time.monotonic() < deadline:
            process = worker.process
            if process is None or process.returncode is not None:
                raise RuntimeError(f"worker exited with code {process.returncode if process else 'unknown'}")
            if await self._probe(worker.project.port):
                return
            await asyncio.sleep(0.2)
        raise TimeoutError("worker readiness timed out")

    async def _probe(self, port: int) -> bool:
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.worker_host, port),
                timeout=0.5,
            )
            writer.write(
                b"GET /_orchestrator/health HTTP/1.1\r\n"
                + f"Host: {self.config.worker_host}:{port}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
            )
            await writer.drain()
            status_line = await asyncio.wait_for(reader.readline(), timeout=0.5)
            return b" 200 " in status_line
        except (OSError, asyncio.TimeoutError):
            return False
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    def _trim_restarts(self, worker: WorkerRuntime, now: float) -> None:
        cutoff = now - worker.project.limits.restart_window_seconds
        while worker.restart_times and worker.restart_times[0] < cutoff:
            worker.restart_times.popleft()

    def _register_failure(self, worker: WorkerRuntime, reason: str) -> None:
        now = time.monotonic()
        worker.restart_times.append(now)
        self._trim_restarts(worker, now)
        worker.last_error = reason
        if len(worker.restart_times) >= worker.project.limits.restart_max:
            worker.circuit_until = now + worker.project.limits.restart_window_seconds
            worker.status = "circuit_open"
        else:
            worker.circuit_until = now + worker.project.limits.restart_backoff_seconds
            worker.status = "degraded"
        logger.error("Project %s isolated: %s", worker.project.project_id, reason)

    async def _stop_worker(self, worker: WorkerRuntime, *, expected: bool, reason: str) -> None:
        process = worker.process
        if process is not None and process.returncode is None:
            try:
                await asyncio.to_thread(self._signal_descendants, process.pid, False)
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                await asyncio.wait_for(process.wait(), timeout=self.config.shutdown_grace_seconds)
            except (ProcessLookupError, asyncio.TimeoutError):
                await asyncio.to_thread(self._signal_descendants, process.pid, True)
                with contextlib.suppress(ProcessLookupError):
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()
        worker.process = None
        worker.started_at = None
        worker.cpu_over_since = None
        if expected:
            worker.status = "stopped"
            worker.last_error = None
        else:
            self._register_failure(worker, reason)

    @staticmethod
    def _signal_descendants(pid: int, force: bool) -> None:
        if psutil is None:
            return
        try:
            descendants = psutil.Process(pid).children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        for child in reversed(descendants):
            try:
                child.kill() if force else child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    async def record_proxy_result(self, project_id: str, status_code: int) -> None:
        worker = self.workers.get(project_id)
        if worker is None:
            return
        worker.last_request = time.monotonic()
        if status_code < 502:
            worker.consecutive_proxy_failures = 0
            return
        worker.consecutive_proxy_failures += 1
        if worker.consecutive_proxy_failures < 3:
            return
        async with worker.lock:
            await self._stop_worker(
                worker,
                expected=False,
                reason=f"upstream returned {status_code} repeatedly",
            )

    def touch(self, project_id: str) -> None:
        worker = self.workers.get(project_id)
        if worker is not None:
            worker.last_request = time.monotonic()

    async def record_proxy_failure(self, project_id: str, reason: str) -> None:
        worker = self.workers.get(project_id)
        if worker is None:
            return
        worker.consecutive_proxy_failures += 1
        if worker.consecutive_proxy_failures < 3:
            worker.last_error = reason
            return
        async with worker.lock:
            await self._stop_worker(worker, expected=False, reason=reason)

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.monitor_interval_seconds)
            self._temp_scan_tick += 1
            total_memory = 0.0
            online: list[WorkerRuntime] = []
            for worker in self.workers.values():
                try:
                    metrics = await self._inspect_worker(worker)
                    if metrics is not None:
                        total_memory += metrics.memory_mb
                        online.append(worker)
                except Exception:
                    logger.exception("Resource monitor failed for %s", worker.project.project_id)

            if (
                self.config.global_memory_budget_mb > 0
                and total_memory > self.config.global_memory_budget_mb
                and online
            ):
                largest = max(online, key=lambda item: item.metrics.memory_mb)
                async with largest.lock:
                    await self._stop_worker(
                        largest,
                        expected=False,
                        reason=(
                            f"global worker memory {total_memory:.0f} MiB exceeded "
                            f"{self.config.global_memory_budget_mb} MiB"
                        ),
                    )

    async def _inspect_worker(self, worker: WorkerRuntime) -> WorkerMetrics | None:
        process = worker.process
        if process is None:
            return None
        if process.returncode is not None:
            async with worker.lock:
                if worker.process is process:
                    await self._stop_worker(
                        worker,
                        expected=False,
                        reason=f"worker exited with code {process.returncode}",
                    )
            return None

        now = time.monotonic()
        if (
            worker.project.limits.idle_timeout_seconds > 0
            and now - worker.last_request > worker.project.limits.idle_timeout_seconds
        ):
            async with worker.lock:
                await self._stop_worker(worker, expected=True, reason="idle timeout")
            return None

        if psutil is None:
            if not self._resource_warning_logged:
                logger.warning("psutil is unavailable; process resource enforcement is disabled.")
                self._resource_warning_logged = True
            return None

        scan_temp = self._temp_scan_tick % 5 == 0
        metrics = await asyncio.to_thread(self._collect_metrics, worker, scan_temp)
        worker.metrics = metrics
        limits = worker.project.limits
        violation: str | None = None
        if limits.memory_mb and metrics.memory_mb > limits.memory_mb:
            violation = f"memory {metrics.memory_mb:.0f} MiB exceeded {limits.memory_mb} MiB"
        elif limits.max_processes and metrics.processes > limits.max_processes:
            violation = f"process count {metrics.processes} exceeded {limits.max_processes}"
        elif limits.max_connections and metrics.connections > limits.max_connections:
            violation = f"connection count {metrics.connections} exceeded {limits.max_connections}"
        elif limits.temp_mb and metrics.temp_mb > limits.temp_mb:
            violation = f"temporary files {metrics.temp_mb:.0f} MiB exceeded {limits.temp_mb} MiB"

        if limits.cpu_percent and metrics.cpu_percent > limits.cpu_percent:
            worker.cpu_over_since = worker.cpu_over_since or now
            if now - worker.cpu_over_since >= limits.cpu_grace_seconds:
                violation = (
                    f"CPU {metrics.cpu_percent:.0f}% exceeded {limits.cpu_percent:.0f}% "
                    f"for {limits.cpu_grace_seconds:.0f}s"
                )
        else:
            worker.cpu_over_since = None

        if violation:
            async with worker.lock:
                await self._stop_worker(worker, expected=False, reason=violation)
            return None
        return metrics

    def _collect_metrics(self, worker: WorkerRuntime, scan_temp: bool) -> WorkerMetrics:
        assert psutil is not None
        assert worker.process is not None
        try:
            root = psutil.Process(worker.process.pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return WorkerMetrics()

        memory = 0
        cpu = 0.0
        connections = 0
        live_processes = 0
        for process in processes:
            try:
                memory += process.memory_info().rss
                cpu += process.cpu_percent(interval=None)
                connections += len(process.net_connections(kind="inet"))
                live_processes += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        temp_mb = worker.metrics.temp_mb
        if scan_temp:
            temp_mb = self._directory_size(self._runtime_dir(worker.project)) / (1024 * 1024)
        return WorkerMetrics(
            memory_mb=memory / (1024 * 1024),
            cpu_percent=cpu,
            processes=live_processes,
            connections=connections,
            temp_mb=temp_mb,
        )

    @staticmethod
    def _directory_size(path: Path) -> int:
        total = 0
        if not path.exists():
            return total
        for root, _, files in os.walk(path):
            for filename in files:
                try:
                    total += (Path(root) / filename).stat().st_size
                except OSError:
                    continue
        return total

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for project_id, project in self.config.projects.items():
            worker = self.workers.get(project_id)
            if worker is None:
                result[project_id] = {
                    "status": "disabled",
                    "reason": project.reason or f"disabled for profile {self.config.profile}",
                }
                continue
            entry: dict[str, Any] = {
                "status": worker.status,
                "restarts": len(worker.restart_times),
            }
            if worker.status == "online":
                entry["resources"] = {
                    "memory_mb": round(worker.metrics.memory_mb, 1),
                    "cpu_percent": round(worker.metrics.cpu_percent, 1),
                    "processes": worker.metrics.processes,
                    "connections": worker.metrics.connections,
                    "temp_mb": round(worker.metrics.temp_mb, 1),
                }
            if worker.circuit_until > time.monotonic():
                entry["retry_after"] = max(1, int(worker.circuit_until - time.monotonic()))
            result[project_id] = entry
        return result
