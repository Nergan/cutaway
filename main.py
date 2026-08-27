"""Compatibility entrypoint for ``uvicorn main:app``."""

from orchestrator.app import app, create_hub_app

__all__ = ["app", "create_hub_app"]
