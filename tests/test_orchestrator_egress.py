"""The project egress forwarder allows listed hosts and refuses the rest."""

from __future__ import annotations

import asyncio

from orchestrator.egress import AllowlistProxy


def test_allowlist_proxy_forwards_a_listed_host_and_rejects_others():
    asyncio.run(_exercise_proxy())


async def _exercise_proxy() -> None:
    async def origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(origin, "127.0.0.1", 8080)
    proxy = AllowlistProxy(("127.0.0.1",), allow_private=True)
    await proxy.start()
    try:
        port = int(proxy.url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"GET http://127.0.0.1:8080/ HTTP/1.1\r\nHost: 127.0.0.1:8080\r\n\r\n"
        )
        await writer.drain()
        allowed = await asyncio.wait_for(reader.read(), timeout=5)
        assert b"hello" in allowed
        writer.close()

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
        await writer.drain()
        denied = await asyncio.wait_for(reader.read(), timeout=5)
        assert b"403" in denied
        writer.close()
    finally:
        await proxy.close()
        server.close()
        await server.wait_closed()
