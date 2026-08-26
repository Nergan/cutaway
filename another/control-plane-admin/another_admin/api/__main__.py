"""python -m another_admin.api — origin control-plane (HF/Render)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("ADMIN_API_HOST", "0.0.0.0")
    port = int(os.environ.get("ADMIN_API_PORT", "8080"))
    uvicorn.run(
        "another_admin.api.app:create_prod_app",
        factory=True,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
