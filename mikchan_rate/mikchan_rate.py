"""Show the macaroni-rate dashboard on /mikchan-rate.

The browser loads the frame and the icon itself. This process does not call
the dashboard: a handshake from the hub to that host times out. If the frame
never reports its height, the page shows an error. A cover hides the link
back to the original chart, which the frame would otherwise show.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()

ORIGIN = "https://mikchan-dashboard-worker.makarka7923.workers.dev"
EMBED_URL = f"{ORIGIN}/embed"
FAVICON = f"{ORIGIN}/favicon.svg"

PAGE = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Курс макарок</title>
  <link rel="icon" href="{FAVICON}" type="image/svg+xml">
  <style>
    html, body {{ margin: 0; min-height: 100%; background: #0a0a0a; color: #f4f1ea; }}
    body {{ font: 16px/1.5 Inter, Segoe UI, sans-serif; }}
    .board {{ position: relative; }}
    .board[hidden], main[hidden] {{ display: none; }}
    iframe {{
      width: 100%;
      height: 760px;
      border: 0;
      background: #0a0a0a;
      color-scheme: dark;
      display: block;
    }}
    .open-cover {{
      position: absolute;
      right: 0;
      bottom: 0;
      width: 9.5rem;
      height: 2.6rem;
      background: #0d0e12;
    }}
    main {{ max-width: 34rem; padding: 2rem; }}
    h1 {{ font-size: 1.4rem; font-weight: 500; margin: 0 0 0.6rem; }}
    p {{ margin: 0; color: #b7b2a8; }}
  </style>
</head>
<body>
  <div class="board">
    <iframe src="{EMBED_URL}" title="Курс макарок"></iframe>
    <div class="open-cover" aria-hidden="true"></div>
  </div>
  <main hidden>
    <h1>Не удалось показать курс</h1>
    <p>Страница курса не отвечает.</p>
  </main>
  <script>
    const board = document.querySelector(".board");
    const frame = board.querySelector("iframe");
    const error = document.querySelector("main");
    let shown = false;
    window.addEventListener("message", (event) => {{
      if (event.source !== frame.contentWindow) return;
      const data = event.data;
      if (!data || data.source !== "mikchan-rate") return;
      shown = true;
      const height = Number(data.height);
      if (height >= 320 && height <= 4000) frame.style.height = Math.ceil(height) + "px";
    }});
    setTimeout(() => {{
      if (shown) return;
      board.hidden = true;
      error.hidden = false;
    }}, 12000);
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(PAGE, headers={"cache-control": "no-store"})
