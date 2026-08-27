"""Streaming HTTP and WebSocket reverse proxy for isolated project workers."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
from typing import Any, AsyncIterator
from urllib.parse import quote

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from .config import ProjectConfig
from .governor import PolicyViolation, ProjectGovernor
from .supervisor import ProjectSupervisor, WorkerUnavailable


HOP_BY_HOP_HEADERS = {
    b"connection",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailer",
    b"transfer-encoding",
    b"upgrade",
}
WEBSOCKET_HANDSHAKE_HEADERS = {
    b"host",
    b"sec-websocket-accept",
    b"sec-websocket-extensions",
    b"sec-websocket-key",
    b"sec-websocket-protocol",
    b"sec-websocket-version",
    b"upgrade",
}


class ProjectProxy:
    def __init__(
        self,
        project: ProjectConfig,
        supervisor: ProjectSupervisor,
        http_client: httpx.AsyncClient,
    ):
        self.project = project
        self.supervisor = supervisor
        self.http_client = http_client
        self.governor = ProjectGovernor(project)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            await self._proxy_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._proxy_websocket(scope, receive, send)

    @staticmethod
    def _client_key(scope: dict[str, Any]) -> str:
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    @staticmethod
    def _full_path(scope: dict[str, Any]) -> str:
        path = str(scope.get("path", "/"))
        root_path = str(scope.get("root_path", ""))
        if root_path and not path.startswith(root_path):
            path = f"{root_path.rstrip('/')}/{path.lstrip('/')}"
        return quote(path, safe="/%:@!$&'()*+,;=-._~")

    def _upstream_url(self, scope: dict[str, Any], *, websocket: bool = False) -> str:
        scheme = "ws" if websocket else "http"
        path = self._full_path(scope)
        query = scope.get("query_string", b"")
        suffix = f"?{query.decode('latin-1')}" if query else ""
        return f"{scheme}://{self.supervisor.config.worker_host}:{self.project.port}{path}{suffix}"

    def _request_headers(self, scope: dict[str, Any], *, websocket: bool = False) -> list[tuple[bytes, bytes]]:
        blocked = HOP_BY_HOP_HEADERS | (WEBSOCKET_HANDSHAKE_HEADERS if websocket else set())
        raw_headers = list(scope.get("headers", []))
        existing_forwarded = next(
            (value for key, value in raw_headers if key.lower() == b"x-forwarded-for"),
            None,
        )
        headers = [
            (key, value)
            for key, value in raw_headers
            if key.lower() not in blocked | {b"x-forwarded-for", b"x-forwarded-proto", b"x-cutaway-project"}
        ]
        client = scope.get("client")
        client_ip = str(client[0]) if client else "unknown"
        forwarded = (
            existing_forwarded + b", " + client_ip.encode("latin-1")
            if existing_forwarded
            else client_ip.encode("latin-1")
        )
        headers.extend(
            [
                (b"x-forwarded-for", forwarded),
                (b"x-forwarded-proto", str(scope.get("scheme", "http")).encode("latin-1")),
                (b"x-cutaway-project", self.project.project_id.encode("ascii")),
            ]
        )
        return headers

    async def _send_error(
        self,
        send: Any,
        status_code: int,
        detail: str,
        retry_after: int | None = None,
    ) -> None:
        body = json.dumps({"detail": detail}, separators=(",", ":")).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        if retry_after is not None:
            headers.append((b"retry-after", str(retry_after).encode("ascii")))
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    async def _proxy_http(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        content_length = next(
            (
                value.decode("latin-1")
                for key, value in scope.get("headers", [])
                if key.lower() == b"content-length"
            ),
            None,
        )
        try:
            self.governor.admit_request(self._client_key(scope), content_length)
            async with self.governor.request_slot():
                await self.supervisor.ensure_running(self.project.project_id)
                await self._stream_http(scope, receive, send)
        except PolicyViolation as exc:
            await self._send_error(send, exc.status_code, exc.detail, exc.retry_after)
        except WorkerUnavailable as exc:
            await self._send_error(send, 503, str(exc), exc.retry_after)

    async def _request_body(self, receive: Any) -> AsyncIterator[bytes]:
        seen = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body = message.get("body", b"")
            if body:
                self.supervisor.touch(self.project.project_id)
                seen += len(body)
                if self.project.limits.request_bytes and seen > self.project.limits.request_bytes:
                    raise PolicyViolation(413, "Project request body limit exceeded.")
                self.governor.record_traffic(len(body))
                yield body
            if not message.get("more_body", False):
                return

    async def _stream_http(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        response: httpx.Response | None = None
        response_started = False
        try:
            headers = self._request_headers(scope)
            has_body = any(
                key.lower() in {b"content-length", b"transfer-encoding"}
                for key, _ in scope.get("headers", [])
            )
            request = self.http_client.build_request(
                str(scope.get("method", "GET")),
                self._upstream_url(scope),
                headers=headers,
                content=self._request_body(receive) if has_body else None,
            )
            async with asyncio.timeout(self.project.limits.request_timeout_seconds):
                response = await self.http_client.send(request, stream=True)
                raw_headers = [
                    (key, value)
                    for key, value in response.headers.raw
                    if key.lower() not in HOP_BY_HOP_HEADERS
                ]
                declared = response.headers.get("content-length")
                if (
                    declared is not None
                    and self.project.limits.response_bytes
                    and int(declared) > self.project.limits.response_bytes
                ):
                    raise PolicyViolation(502, "Project response body limit exceeded.")
                await send(
                    {
                        "type": "http.response.start",
                        "status": response.status_code,
                        "headers": raw_headers,
                    }
                )
                response_started = True
                seen = 0
                async for chunk in response.aiter_raw():
                    self.supervisor.touch(self.project.project_id)
                    seen += len(chunk)
                    if self.project.limits.response_bytes and seen > self.project.limits.response_bytes:
                        raise PolicyViolation(502, "Project response body limit exceeded.")
                    self.governor.record_traffic(len(chunk))
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                await self.supervisor.record_proxy_result(self.project.project_id, response.status_code)
        except PolicyViolation:
            if response_started:
                with contextlib.suppress(Exception):
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                return
            raise
        except TimeoutError:
            await self.supervisor.record_proxy_failure(self.project.project_id, "upstream request timed out")
            if not response_started:
                await self._send_error(send, 504, "Project request timed out.", 1)
        except httpx.HTTPError as exc:
            await self.supervisor.record_proxy_failure(
                self.project.project_id,
                f"upstream transport failed: {type(exc).__name__}",
            )
            if not response_started:
                await self._send_error(send, 502, "Project worker connection failed.", 1)
        finally:
            if response is not None:
                await response.aclose()

    async def _proxy_websocket(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        try:
            self.governor.admit_request(self._client_key(scope), None)
            async with self.governor.websocket_slot():
                await self.supervisor.ensure_running(self.project.project_id)
                await self._relay_websocket(scope, receive, send)
        except (PolicyViolation, WorkerUnavailable) as exc:
            retry = exc.retry_after if isinstance(exc, (PolicyViolation, WorkerUnavailable)) else None
            reason = str(exc)[:120]
            await send({"type": "websocket.close", "code": 1013, "reason": reason})
            if retry:
                await asyncio.sleep(0)

    async def _relay_websocket(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        first = await receive()
        if first["type"] != "websocket.connect":
            return

        headers = [
            (key.decode("latin-1"), value.decode("latin-1"))
            for key, value in self._request_headers(scope, websocket=True)
        ]
        connect_kwargs: dict[str, Any] = {
            "subprotocols": list(scope.get("subprotocols", [])) or None,
            "open_timeout": self.project.limits.startup_timeout_seconds,
            "max_size": self.project.limits.websocket_message_bytes,
        }
        parameters = inspect.signature(websockets.connect).parameters
        if "additional_headers" in parameters:
            connect_kwargs["additional_headers"] = headers
        else:  # websockets < 14
            connect_kwargs["extra_headers"] = headers

        try:
            async with websockets.connect(
                self._upstream_url(scope, websocket=True),
                **connect_kwargs,
            ) as upstream:
                await self.supervisor.record_proxy_result(self.project.project_id, 101)
                await send(
                    {
                        "type": "websocket.accept",
                        "subprotocol": upstream.subprotocol,
                        "headers": [],
                    }
                )
                async with asyncio.timeout(self.project.limits.websocket_lifetime_seconds):
                    client_task = asyncio.create_task(
                        self._websocket_client_to_upstream(receive, upstream)
                    )
                    upstream_task = asyncio.create_task(
                        self._websocket_upstream_to_client(upstream, send)
                    )
                    done, pending = await asyncio.wait(
                        {client_task, upstream_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    for task in pending:
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    for task in done:
                        task.result()
        except TimeoutError:
            await send({"type": "websocket.close", "code": 1001, "reason": "Session time limit reached."})
        except (OSError, ConnectionClosed, websockets.WebSocketException) as exc:
            await self.supervisor.record_proxy_failure(
                self.project.project_id,
                f"websocket transport failed: {type(exc).__name__}",
            )
            with contextlib.suppress(Exception):
                await send({"type": "websocket.close", "code": 1011, "reason": "Worker disconnected."})

    async def _websocket_client_to_upstream(self, receive: Any, upstream: Any) -> None:
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                await upstream.close(code=message.get("code", 1000))
                return
            if message["type"] != "websocket.receive":
                continue
            data = message.get("bytes")
            if data is None:
                data = message.get("text", "")
            size = len(data) if isinstance(data, bytes) else len(data.encode("utf-8"))
            if size > self.project.limits.websocket_message_bytes:
                raise PolicyViolation(413, "WebSocket message limit exceeded.")
            self.governor.record_traffic(size)
            self.supervisor.touch(self.project.project_id)
            await upstream.send(data)

    async def _websocket_upstream_to_client(self, upstream: Any, send: Any) -> None:
        async for data in upstream:
            size = len(data) if isinstance(data, bytes) else len(data.encode("utf-8"))
            if size > self.project.limits.websocket_message_bytes:
                raise PolicyViolation(502, "WebSocket message limit exceeded.")
            self.governor.record_traffic(size)
            self.supervisor.touch(self.project.project_id)
            message = {"type": "websocket.send"}
            message["bytes" if isinstance(data, bytes) else "text"] = data
            await send(message)
