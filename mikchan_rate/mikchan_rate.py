"""Show the macaroni-rate dashboard on /mikchan-rate.

The dashboard publishes a frame that may be embedded. The browser loads that
frame itself. If the frame never reports its height, the page shows an error.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()

EMBED = "https://mikchan-dashboard-worker.makarka7923.workers.dev/embed"

PAGE = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Курс макарок</title>
  <style>
    html, body {{ margin: 0; min-height: 100%; background: #0a0a0a; color: #f4f1ea; }}
    body {{ font: 16px/1.5 Inter, Segoe UI, sans-serif; }}
    iframe {{
      width: 100%;
      height: 760px;
      border: 0;
      background: #0a0a0a;
      color-scheme: dark;
      display: block;
    }}
    iframe[hidden], main[hidden] {{ display: none; }}
    main {{ max-width: 34rem; padding: 2rem; }}
    h1 {{ font-size: 1.4rem; font-weight: 500; margin: 0 0 0.6rem; }}
    p {{ margin: 0; color: #b7b2a8; }}
  </style>
</head>
<body>
  <iframe src="{EMBED}" title="Курс макарок"></iframe>
  <main hidden>
    <h1>Не удалось показать курс</h1>
    <p>Страница курса не отвечает.</p>
  </main>
  <script>
    const frame = document.querySelector("iframe");
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
      frame.hidden = true;
      error.hidden = false;
    }}, 12000);
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(PAGE)
