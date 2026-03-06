import asyncio
import random
from datetime import datetime
import httpx
from .config import CLIENT_MAX_AGE, USER_AGENTS

ip_clients = {}
ip_clients_lock = asyncio.Lock()


async def get_client_for_ip(ip: str) -> tuple[httpx.AsyncClient, str]:
    async with ip_clients_lock:
        now = datetime.utcnow().timestamp()
        # Очистка старых клиентов
        to_delete = []
        for stored_ip, (_, last_used, _) in ip_clients.items():
            if now - last_used > CLIENT_MAX_AGE:
                to_delete.append(stored_ip)
        for stored_ip in to_delete:
            client_to_close, _, _ = ip_clients.pop(stored_ip)
            await client_to_close.aclose()

        if ip in ip_clients:
            client, _, ua = ip_clients[ip]
            ip_clients[ip] = (client, now, ua)
        else:
            ua = random.choice(USER_AGENTS)
            client = httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                max_redirects=5,
                limits=httpx.Limits(max_keepalive_connections=10)
            )
            ip_clients[ip] = (client, now, ua)
        return client, ua


async def shutdown_clients():
    async with ip_clients_lock:
        for ip, (client, _, _) in ip_clients.items():
            await client.aclose()
        ip_clients.clear()