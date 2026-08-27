"""Bounded subprocess execution shared by resource-intensive projects."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


_HEAVY_JOBS = max(1, int(os.getenv("CUTAWAY_HEAVY_JOBS", "1")))
_SUBPROCESS_SLOTS = asyncio.Semaphore(_HEAVY_JOBS)
_OUTPUT_LIMIT = max(4096, int(os.getenv("CUTAWAY_SUBPROCESS_LOG_BYTES", "65536")))


class SubprocessFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool = False
    stderr_truncated: bool = False


async def _read_limited(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, bool]:
    if stream is None:
        return b"", False
    chunks: list[bytes] = []
    size = 0
    truncated = False
    while True:
        chunk = await stream.read(16 * 1024)
        if not chunk:
            break
        if size < limit:
            retained = chunk[: limit - size]
            chunks.append(retained)
            size += len(retained)
            truncated = truncated or len(retained) < len(chunk)
        else:
            truncated = True
    return b"".join(chunks), truncated


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    with contextlib.suppress(Exception):
        await process.wait()


async def run_process(
    args: Sequence[str | os.PathLike[str]],
    *,
    timeout: float,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    check: bool = True,
    allowed_returncodes: frozenset[int] = frozenset({0}),
    output_limit: int = _OUTPUT_LIMIT,
) -> ProcessResult:
    """Run a child in its own killable group with bounded output buffers."""
    argv = tuple(str(item) for item in args)
    if not argv:
        raise ValueError("Subprocess argv must not be empty.")
    if timeout <= 0:
        raise ValueError("Subprocess timeout must be positive.")

    child_env = dict(env) if env is not None else os.environ.copy()
    if (
        "CUTAWAY_PROJECT_NETWORK_HOSTS" in child_env
        and not child_env["CUTAWAY_PROJECT_NETWORK_HOSTS"].strip()
    ):
        child_env.update(
            {
                "ALL_PROXY": "http://127.0.0.1:9",
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "NO_PROXY": "127.0.0.1,localhost",
            }
        )

    kwargs = {
        "cwd": str(Path(cwd)) if cwd is not None else None,
        "env": child_env,
        "stdin": asyncio.subprocess.DEVNULL,
        "stdout": asyncio.subprocess.PIPE if capture_stdout else asyncio.subprocess.DEVNULL,
        "stderr": asyncio.subprocess.PIPE if capture_stderr else asyncio.subprocess.DEVNULL,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True

    async with _SUBPROCESS_SLOTS:
        process = await asyncio.create_subprocess_exec(*argv, **kwargs)
        stdout_task = asyncio.create_task(_read_limited(process.stdout, output_limit))
        stderr_task = asyncio.create_task(_read_limited(process.stderr, output_limit))
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            await _kill_process_tree(process)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise SubprocessFailure(f"Process timed out after {timeout:g} seconds.") from exc

        (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
            stdout_task,
            stderr_task,
        )
        result = ProcessResult(
            argv,
            int(process.returncode or 0),
            stdout,
            stderr,
            stdout_truncated,
            stderr_truncated,
        )
        if check and result.returncode not in allowed_returncodes:
            raise SubprocessFailure(f"Process failed with exit code {result.returncode}.")
        return result
