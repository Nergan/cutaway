"""Stdlib checks for formular limits that must not depend on conversion engines."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from formular.core.errors import FormularError
from formular.core.language import detect_language
from formular.core.models import ModelCache, ModelSpec, license_allowed
from formular.core.ffmpeg_flags import custom_ffmpeg_args
from formular.core.plan import path_cost, shortest_path
from formular.core.workspace import WorkspaceStore
from formular.core.xmlio import assert_plain_xml
from orchestrator.config import ProjectLimits, load_runtime_config
from orchestrator.supervisor import busy_marker_fresh, cpu_contribution

_SCRATCH = Path(__file__).resolve().parents[1] / ".pytest-tmp" / "formular-safety"


def _scratch(name: str) -> Path:
    folder = _SCRATCH / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def test_ffmpeg_whitelist_accepts_scale_and_rejects_file_filters():
    assert custom_ffmpeg_args("-crf 23 -vf scale=1280:720") == [
        "-crf",
        "23",
        "-vf",
        "scale=1280:720",
    ]
    assert custom_ffmpeg_args("-threads 2 -vn") == ["-threads", "2", "-vn"]
    for sample in (
        "-vf drawtext=textfile=secret",
        "-i other.mp4",
        "-vf scale=../out",
        "-threads 4",
    ):
        with pytest.raises(FormularError) as caught:
            custom_ffmpeg_args(sample)
        assert caught.value.status == 422


def test_xml_rejects_doctype_and_oversized_input():
    assert_plain_xml("<root><item>ok</item></root>")
    with pytest.raises(FormularError) as doctype:
        assert_plain_xml("<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><foo>&xxe;</foo>")
    assert doctype.value.status == 422
    with pytest.raises(FormularError) as huge:
        assert_plain_xml("a" * 8_000_001)
    assert huge.value.status == 413


def _fewest_hops(edges, start, goal):
    if start == goal:
        return [start]
    queue = [(start, [start])]
    seen = set()
    while queue:
        node, path = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        for nxt in edges.get(node, []):
            nxt_path = path + [nxt]
            if nxt == goal:
                return nxt_path
            queue.append((nxt, nxt_path))
    return None


def test_interface_targets_match_the_weighted_plan():
    from formular.core.registry import ALLOWED_CONVERSIONS, DIRECT_EDGES

    for source, targets in ALLOWED_CONVERSIONS.items():
        for target in targets:
            weighted = shortest_path(DIRECT_EDGES, source, target)
            hopped = _fewest_hops(DIRECT_EDGES, source, target)
            assert weighted is not None and hopped is not None
            assert path_cost(weighted) <= path_cost(hopped)


def test_public_catalog_marks_later_stages_unavailable():
    from formular.core.registry import public_operations

    catalog = public_operations()
    later = {item["id"]: item for item in catalog if not item["available"]}
    assert set(later) == {"pdf.translate", "speech.transcribe", "bytecode.recover"}
    assert all(item["reason"] for item in later.values())


def test_planner_prefers_a_cheap_path_and_reports_missing_goals():
    edges = {"txt": ["md", "pdf"], "md": ["html"], "html": ["pdf"]}
    assert shortest_path(edges, "txt", "html") == ["txt", "md", "html"]
    assert shortest_path(edges, "txt", "txt") == ["txt"]
    assert shortest_path(edges, "html", "md") is None
    assert path_cost(["txt", "md", "html"]) == 2.0


def test_workspace_hashes_ids_and_enforces_ttl_and_budget():
    tmp_path = _scratch("workspace")
    store = WorkspaceStore(tmp_path, ttl_seconds=60, max_total_bytes=40, max_workspace_bytes=30)
    info = store.create()
    assert info.path.name != info.token
    assert info.path == tmp_path / __import__("hashlib").sha256(info.token.encode("ascii")).hexdigest()
    opened = store.open(info.token)
    assert opened.expires == info.expires

    with pytest.raises(FormularError) as missing:
        store.open("not-a-real-workspace-token-value")
    assert missing.value.status == 404

    meta = info.path / "meta.json"
    meta.write_text('{"created": 1, "expires": 1}', encoding="utf-8")
    with pytest.raises(FormularError) as expired:
        store.open(info.token)
    assert expired.value.status == 410
    assert store.sweep() >= 0
    assert not info.path.exists()

    room = WorkspaceStore(tmp_path / "full", ttl_seconds=60, max_total_bytes=200, max_workspace_bytes=200)
    kept = room.create()
    (kept.path / "blob").write_bytes(b"x" * 80)
    full_store = WorkspaceStore(room.root, ttl_seconds=60, max_total_bytes=50, max_workspace_bytes=200)
    with pytest.raises(FormularError) as full:
        full_store.create()
    assert full.value.status == 429


def test_heavy_jobs_stay_one_when_page_concurrency_rises():
    derived = ProjectLimits(max_concurrency=6)
    assert derived.resolved_heavy_jobs() == 2
    pinned = ProjectLimits.from_mapping({"max_concurrency": 6, "heavy_jobs": 1})
    assert pinned.resolved_heavy_jobs() == 1


def test_language_cues_cover_clear_sentences():
    assert detect_language("This is a plain English sentence and it is long enough.")["language"] == "en"
    assert detect_language("Это простой русский текст, и в нём есть слова.")["language"] == "ru"
    assert detect_language("Це український текст, і в ньому є свої літери.")["language"] == "uk"
    assert detect_language("Das ist ein deutscher Satz und der Text ist klar.")["language"] == "de"
    assert detect_language("hi")["language"] == "unknown"
    assert detect_language("The model answer is marked.")["ai"] is True


def test_model_license_rejects_noncommercial_weights():
    assert license_allowed("Apache-2.0")
    assert license_allowed("CC-BY-4.0")
    assert not license_allowed("CC-BY-NC-4.0")
    assert not license_allowed("other")


def test_model_cache_removes_weights_when_the_task_releases_them(monkeypatch):
    payload = b"model-weights"
    digest = hashlib.sha256(payload).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = payload
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CUTAWAY_PROJECT_NETWORK_HOSTS", "127.0.0.1")
    monkeypatch.setenv("CUTAWAY_PROJECT_ALLOW_PRIVATE_NETWORK", "1")
    monkeypatch.setenv("CUTAWAY_PROJECT_NETWORK_RPM", "0")
    try:
        cache = ModelCache(_scratch("models"), max_total_bytes=1024)
        spec = ModelSpec(
            "org/example",
            "http://127.0.0.1:8080/weights",
            "Apache-2.0",
            digest,
            max_bytes=1024,
        )
        first = cache.acquire(spec)
        second = cache.acquire(spec)
        assert first.read_bytes() == payload
        cache.release(spec.model_id)
        assert second.is_file()
        cache.release(spec.model_id)
        assert not first.exists()
    finally:
        server.shutdown()
        server.server_close()


def test_nice_background_cpu_does_not_count_toward_the_kill():
    assert cpu_contribution(200, 19, 19) == 0
    assert cpu_contribution(200, 0, 19) == 200
    assert cpu_contribution(200, 19, 0) == 200


def test_hf_formular_can_download_weights_inside_the_memory_budget():
    config = load_runtime_config(Path(__file__).resolve().parents[1], profile="hf", isolation="isolated")
    formular = config.projects["formular"]
    assert formular.limits.memory_mb == 5120
    assert formular.limits.temp_mb == 8192
    assert formular.limits.fsize_mb == 4096
    assert formular.limits.cpu_exempt_nice == 19
    assert formular.network.enforce_allowlist is True
    assert "huggingface.co" in formular.network.allowed_hosts
    declared = sum(project.limits.memory_mb for project in config.projects.values() if project.run)
    assert declared <= config.global_memory_budget_mb


def test_busy_marker_blocks_idle_stop_only_while_fresh():
    marker = _scratch("busy") / "busy"
    assert busy_marker_fresh(marker) is False
    marker.write_text("", encoding="utf-8")
    now = time.time()
    assert busy_marker_fresh(marker, now=now) is True
    assert busy_marker_fresh(marker, now=now + 120) is False
