"""Локальный выход только на разрешённые хосты.

Пустой список хостов по-прежнему глушится в супервизоре. Если список задан и
включена проверка, процесс проекта ходит наружу только через этот выход:
остальные адреса обрываются здесь, а не политикой внутри приложения.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from urllib.parse import urlsplit

from shared_network import NetworkPolicyError, preferred_outbound_ip, validate_outbound_url


class AllowlistProxy:
    def __init__(
        self,
        allowed_hosts: tuple[str, ...],
        *,
        allow_private: bool = False,
        requests_per_minute: int = 0,
    ):
        self.allowed_hosts = tuple(host.lower().rstrip(".") for host in allowed_hosts)
        self.allow_private = allow_private
        self.requests_per_minute = requests_per_minute
        self.url = ""
        self._server: asyncio.AbstractServer | None = None
        self._times: deque[float] = deque()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        sockets = getattr(self._server, "sockets", None) or []
        port = sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"

    async def close(self) -> None:
        server = self._server
        self._server = None
        if server is None:
            return
        server.close()
        await server.wait_closed()

    def _admit(self, host: str, port: int) -> str:
        if self.requests_per_minute > 0:
            now = time.monotonic()
            while self._times and self._times[0] < now - 60:
                self._times.popleft()
            if len(self._times) >= self.requests_per_minute:
                raise NetworkPolicyError("Outbound request budget exceeded.")
            self._times.append(now)
        scheme = "https" if port == 443 else "http"
        validate_outbound_url(
            f"{scheme}://{host}:{port}/",
            allowed_hosts=self.allowed_hosts,
            allow_private=self.allow_private,
        )
        if self.allow_private:
            return host
        return preferred_outbound_ip(host, port, allow_private=False)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            writer.close()
            return
        line = header.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        parts = line.split(" ")
        if len(parts) < 2:
            await self._reject(writer, 400)
            return
        method, target = parts[0].upper(), parts[1]
        try:
            if method == "CONNECT":
                host, port = _split_host_port(target, 443)
                destination = self._admit(host, port)
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                remote_reader, remote_writer = await asyncio.open_connection(destination, port)
            else:
                parsed = urlsplit(target)
                host = parsed.hostname or ""
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                destination = self._admit(host, port)
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                rewritten = f"{method} {path} HTTP/1.1\r\n".encode("ascii")
                remote_reader, remote_writer = await asyncio.open_connection(destination, port)
                remote_writer.write(rewritten + _forward_headers(header))
                await remote_writer.drain()
        except (NetworkPolicyError, OSError, ValueError):
            await self._reject(writer, 403)
            return
        await asyncio.gather(
            _pipe(reader, remote_writer),
            _pipe(remote_reader, writer),
        )

    @staticmethod
    async def _reject(writer: asyncio.StreamWriter, status: int) -> None:
        writer.write(f"HTTP/1.1 {status} Denied\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        writer.close()


def _split_host_port(target: str, default_port: int) -> tuple[str, int]:
    if target.startswith("["):
        host, _, port_text = target[1:].partition("]")
        port = int(port_text[1:]) if port_text.startswith(":") else default_port
        return host, port
    host, separator, port_text = target.rpartition(":")
    if not separator:
        return target, default_port
    return host, int(port_text)


def _forward_headers(header: bytes) -> bytes:
    lines = header.split(b"\r\n")[1:]
    kept = [
        line
        for line in lines
        if line and not line.lower().startswith((b"proxy-connection:", b"proxy-authorization:"))
    ]
    return b"\r\n".join(kept) + b"\r\n\r\n"


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, OSError, asyncio.CancelledError):
        return
    finally:
        writer.close()
