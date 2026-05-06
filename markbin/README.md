# Markbin

Markbin is a minimalist, fast, and secure Markdown sharing service—a “Pastebin for Markdown.” It combines an Obsidian-like live preview editor with dynamic table of contents generation and secure database-backed storage, all wrapped in a custom “Sakura‑Vader” dark theme.

## Features

- **Live Preview Editing** – Powered by [Vditor](https://github.com/Vanessa219/vditor) in instant‑rendering (`ir`) mode. Markdown syntax hides as you type, showing rich text immediately.
- **Dynamic Table of Contents** – Automatically extracts headings (using `markdown‑it` for robust parsing) and builds a clickable, indented sidebar that scrolls the document or editor smoothly.
- **Multiple Input Methods** – Type directly, drag & drop `.md` / `.txt` files, or click the upload button to load content into the editor.
- **Local Draft Persistence** – Unfinished snippets are saved to `localStorage` and restored automatically when you return to the editor.
- **Secure Read Mode** – View saved documents with content sanitised by [DOMPurify](https://github.com/cure53/DOMPurify). Rendered with `markdown‑it` and the `task‑lists` plugin for full GitHub‑Flavored Markdown compatibility.
- **Copy Raw Markdown** – In view mode, one click copies the original Markdown source to the clipboard.
- **Custom Hotkeys** – `Ctrl+S` / `Cmd+S` saves the snippet instantly (instead of opening the browser save dialog), with a spinner animation and toast feedback.
- **Adaptive Navigation Bar** – A collapsible panel on mobile slides up from the bottom; on desktop it lives at the top. The toggle button animates smoothly and swaps icons depending on screen size.
- **Standalone or Embedded** – Designed to run independently via `uvicorn` or as a sub‑mounted router inside a FastAPI superproject (e.g., Cutaway).

## Theme

Markbin uses a custom **“Sakura‑Vader”** dark theme. The colour palette (`#222222` background, `#e06c75` accent) keeps the interface quiet and focused. Distractions like toolbars are hidden until you need them.

## Technology Stack

| Layer          | Libraries / Tools                                                                          |
|----------------|--------------------------------------------------------------------------------------------|
| Editor         | [Vditor](https://github.com/Vanessa219/vditor) (IR mode, dark theme)                       |
| Markdown       | [markdown‑it](https://github.com/markdown-it/markdown-it) 14.1.0 + `markdown‑it‑task‑lists` |
| Sanitisation   | [DOMPurify](https://github.com/cure53/DOMPurify) 3.0.6                                     |
| Backend        | [FastAPI](https://fastapi.tiangolo.com/), [Motor](https://motor.readthedocs.io/) (async MongoDB) |
| Database       | MongoDB (collection `markbins.docs`)                                                       |
| Frontend       | Vanilla JavaScript, [Bootstrap Icons](https://icons.getbootstrap.com/)                     |
| Templating     | Jinja2 (via FastAPI)                                                                       |

## API Endpoints

All endpoints are prefixed with `/markbin` (configurable in the FastAPI router).

| Method | Path               | Description                                                                                   |
|--------|--------------------|-----------------------------------------------------------------------------------------------|
| `GET`  | `/`                | Edit mode – empty editor with draft restoration.                                              |
| `GET`  | `/{uuid}`          | View mode – renders the stored Markdown document as sanitised HTML.                           |
| `POST` | `/api/save`        | Saves a raw Markdown payload. Returns `{"uuid": "<8‑char hex>"}`.                             |
| `GET`  | `/api/docs/{uuid}` | Retrieves the raw Markdown content for a given UUID. Returns `{"content": "..."}`.            |

### Embedding in Another FastAPI App

Mount the static files and include the router with the prefix your superproject expects:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from markbin.markbin import router

app = FastAPI()
app.mount('/markbin/static', StaticFiles(directory='markbin/static'), name='markbin-static')
app.mount('/markbin/scripts', StaticFiles(directory='markbin/scripts'), name='markbin-scripts')
app.include_router(router, prefix='/markbin')
```

## File Structure

```
markbin/
├── markbin.py          # FastAPI router, endpoints, MongoDB connection
├── main.py             # Standalone entry point
├── markbin.html        # Jinja2 template, static asset links
├── static/
│   ├── style.css       # Sakura‑Vader theme, responsive layout, Vditor overrides
│   └── favicon.png
├── scripts/
│   └── app.js          # Editor initialisation, TOC, markdown‑it config, UI logic
└── README.md
```