import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, Request

from orchestrator.config import load_runtime_config
from orchestrator.proxy import ProjectProxy


ROOT = Path(__file__).resolve().parents[1]


class FakeSupervisor:
    def __init__(self):
        self.config = SimpleNamespace(worker_host="127.0.0.1")
        self.ensure_calls = 0
        self.results = []
        self.failures = []

    async def ensure_running(self, project_id):
        self.ensure_calls += 1
        return SimpleNamespace()

    async def record_proxy_result(self, project_id, status_code):
        self.results.append((project_id, status_code))

    async def record_proxy_failure(self, project_id, reason):
        self.failures.append((project_id, reason))

    def touch(self, project_id):
        pass


def test_http_proxy_preserves_path_headers_and_streamed_body():
    async def scenario():
        project = load_runtime_config(ROOT, profile="hf").projects["toadcode"]
        project = replace(
            project,
            limits=replace(
                project.limits,
                request_bytes=1024,
                response_bytes=1024,
                traffic_bytes_per_minute=4096,
            ),
        )
        upstream = FastAPI()

        @upstream.post("/{path:path}")
        async def echo(path: str, request: Request):
            return {
                "path": request.url.path,
                "query": request.url.query,
                "body": (await request.body()).decode(),
                "forwarded": request.headers["x-forwarded-for"],
                "project": request.headers["x-cutaway-project"],
            }

        upstream_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://worker",
        )
        supervisor = FakeSupervisor()
        outer = FastAPI()
        outer.mount(project.prefix, ProjectProxy(project, supervisor, upstream_client))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=outer),
            base_url="https://hub.example",
        ) as client:
            response = await client.post(
                "/toadcode/api/echo?value=1",
                content=b"hello",
            )

        await upstream_client.aclose()
        assert response.status_code == 200
        assert response.json() == {
            "path": "/toadcode/api/echo",
            "query": "value=1",
            "body": "hello",
            "forwarded": "127.0.0.1",
            "project": "toadcode",
        }
        assert supervisor.ensure_calls == 1
        assert supervisor.results == [("toadcode", 200)]

    asyncio.run(scenario())


def test_http_proxy_rejects_body_before_starting_worker():
    async def scenario():
        project = load_runtime_config(ROOT, profile="hf").projects["toadcode"]
        project = replace(project, limits=replace(project.limits, request_bytes=4))
        upstream = FastAPI()
        upstream_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=upstream))
        supervisor = FakeSupervisor()
        outer = FastAPI()
        outer.mount(project.prefix, ProjectProxy(project, supervisor, upstream_client))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=outer),
            base_url="http://hub",
        ) as client:
            response = await client.post("/toadcode/api/save", content=b"12345")

        await upstream_client.aclose()
        assert response.status_code == 413
        assert supervisor.ensure_calls == 0

    asyncio.run(scenario())
