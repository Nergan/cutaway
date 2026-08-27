import asyncio
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.config import load_runtime_config
from orchestrator.governor import PolicyViolation, ProjectGovernor
from orchestrator.supervisor import ProjectSupervisor, WorkerUnavailable
from shared_network import NetworkPolicyError, validate_outbound_url
from shared_runtime import SubprocessFailure, run_process


ROOT = Path(__file__).resolve().parents[1]


def _project_with(**limit_overrides):
    project = load_runtime_config(ROOT, profile="hf").projects["toadcode"]
    return replace(project, limits=replace(project.limits, **limit_overrides))


def test_governor_rejects_declared_and_streamed_traffic_limits():
    governor = ProjectGovernor(
        _project_with(request_bytes=10, traffic_bytes_per_minute=12)
    )

    with pytest.raises(PolicyViolation) as declared:
        governor.admit_request("client", "11")
    assert declared.value.status_code == 413

    governor.admit_request("client", "10")
    governor.record_traffic(8)
    with pytest.raises(PolicyViolation) as traffic:
        governor.record_traffic(5)
    assert traffic.value.status_code == 429


def test_governor_rate_and_concurrency_limits():
    async def scenario():
        governor = ProjectGovernor(
            _project_with(
                request_rate=1,
                request_window_seconds=60,
                max_concurrency=1,
                queue_timeout_seconds=0.01,
            )
        )
        governor.admit_request("one", None)
        with pytest.raises(PolicyViolation) as rate:
            governor.admit_request("one", None)
        assert rate.value.status_code == 429

        async with governor.request_slot():
            with pytest.raises(PolicyViolation) as concurrency:
                async with governor.request_slot():
                    pass
            assert concurrency.value.status_code == 503

    asyncio.run(scenario())


def test_outbound_policy_blocks_ports_private_networks_and_unknown_hosts(monkeypatch):
    monkeypatch.setenv("CUTAWAY_PROJECT_NETWORK_RPM", "0")

    parsed = validate_outbound_url(
        "https://api.github.com/repos/example/repo",
        allowed_hosts=("api.github.com",),
        resolve_dns=False,
    )
    assert parsed.hostname == "api.github.com"

    with pytest.raises(NetworkPolicyError):
        validate_outbound_url(
            "https://example.com:444/path",
            allowed_hosts=("example.com",),
            resolve_dns=False,
        )
    with pytest.raises(NetworkPolicyError):
        validate_outbound_url(
            "https://unlisted.example/path",
            allowed_hosts=("example.com",),
            resolve_dns=False,
        )
    with pytest.raises(NetworkPolicyError):
        validate_outbound_url(
            "http://127.0.0.1/",
            allowed_hosts=("127.0.0.1",),
        )


def test_shared_subprocess_runner_captures_output_and_kills_timeout():
    async def scenario():
        result = await run_process(
            [sys.executable, "-c", "print('bounded')"],
            timeout=5,
            capture_stdout=True,
        )
        assert result.stdout.strip() == b"bounded"

        with pytest.raises(SubprocessFailure, match="timed out"):
            await run_process(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.05,
            )

    asyncio.run(scenario())


def test_supervisor_omits_disabled_projects():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    supervisor = ProjectSupervisor(config)

    assert "another" not in supervisor.workers
    assert "yellow_mirror" not in supervisor.workers
    assert "toadcode" in supervisor.workers
    snapshot = supervisor.snapshot()
    assert snapshot["another"]["status"] == "disabled"
    assert snapshot["yellow_mirror"]["status"] == "disabled"


def test_supervisor_opens_circuit_after_restart_budget():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    supervisor = ProjectSupervisor(config)
    worker = supervisor.workers["toadcode"]
    worker.project = replace(
        worker.project,
        limits=replace(
            worker.project.limits,
            restart_max=2,
            restart_window_seconds=60,
            restart_backoff_seconds=1,
        ),
    )

    supervisor._register_failure(worker, "first crash")
    assert worker.status == "degraded"
    supervisor._register_failure(worker, "second crash")
    assert worker.status == "circuit_open"
    assert worker.circuit_until > time.monotonic()

    snapshot = supervisor.snapshot()
    assert snapshot["toadcode"]["status"] == "circuit_open"
    assert snapshot["toadcode"]["retry_after"] >= 1


def test_ensure_running_respects_open_circuit():
    async def scenario():
        config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
        supervisor = ProjectSupervisor(config)
        worker = supervisor.workers["kanban"]
        worker.circuit_until = time.monotonic() + 30
        with pytest.raises(WorkerUnavailable, match="temporarily isolated"):
            await supervisor.ensure_running("kanban")
        assert worker.status == "circuit_open"

    asyncio.run(scenario())


def test_websocket_disabled_when_quota_is_zero():
    async def scenario():
        governor = ProjectGovernor(_project_with(max_websockets=0))
        with pytest.raises(PolicyViolation) as disabled:
            async with governor.websocket_slot():
                pass
        assert disabled.value.status_code == 403

        limited = ProjectGovernor(_project_with(max_websockets=1))
        async with limited.websocket_slot():
            with pytest.raises(PolicyViolation) as busy:
                async with limited.websocket_slot():
                    pass
            assert busy.value.status_code == 503

    asyncio.run(scenario())
