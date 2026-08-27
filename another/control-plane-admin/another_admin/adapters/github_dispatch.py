"""Триггер GitHub Actions: в payload только job_id, не enrollment_token."""

from __future__ import annotations

import logging

import httpx

from another_admin.api.config import ApiConfig

logger = logging.getLogger(__name__)


def dispatch_installer(cfg: ApiConfig, job_id: str) -> bool:
    repo = (cfg.github_repo or "").strip()
    token = (cfg.github_dispatch_token or "").strip()
    if not repo or not token or "/" not in repo:
        logger.warning("installer dispatch skipped: GITHUB_REPO / GITHUB_DISPATCH_TOKEN empty")
        return False
    event = (cfg.github_dispatch_event or "another-installer").strip()
    url = f"https://api.github.com/repos/{repo}/dispatches"
    try:
        response = httpx.post(
            url,
            json={"event_type": event, "client_payload": {"job_id": job_id}},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
        )
    except httpx.HTTPError:
        logger.exception("installer dispatch request failed")
        return False
    if response.status_code >= 300:
        logger.error("installer dispatch failed status=%s", response.status_code)
        return False
    return True
