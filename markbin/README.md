# Markbin

Markbin is a minimalist, fast, and secure Markdown sharing service—a “Pastebin for Markdown.” It combines an Obsidian-like live preview editor with dynamic table of contents generation and secure database-backed storage, all wrapped in a custom “Sakura‑Vader” dark theme.

## Features

- **Live Preview Editing** – Powered by [Vditor](https://github.com/Vanessa219/vditor) in instant‑rendering (`ir`) mode. Markdown syntax hides as you type, showing rich text immediately.
- **Unified View Mode** – Instead of using separate parsers, view mode relies on Vditor's native preview engine. This guarantees 100% visual parity between what you type (including math blocks, Mermaid diagrams, and complex tables) and what is shared.
- **Dynamic Table of Contents** – Automatically extracts headings and builds a clickable, indented sidebar that scrolls the document or editor smoothly.
- **Multiple Input Methods** – Type directly, click the upload button, or drag & drop `.md` / `.txt` files. Dropping files safely prompts the user to either replace the draft or append the text at the cursor.
- **Local Draft Persistence** – Unfinished snippets are saved to `localStorage` and restored automatically when you return to the editor.
- **Visual Unsaved Indicator** – The save button provides immediate visual feedback (a bright notification dot) whenever the editor contains unsaved changes.
- **Copy Raw Markdown** – In view mode, one click copies the original Markdown source to the clipboard.
- **Custom Hotkeys** – `Ctrl+S` / `Cmd+S` saves the snippet instantly (instead of opening the browser save dialog), with a spinner animation and toast feedback.
- **Adaptive Navigation Bar** – A collapsible panel on mobile slides up from the bottom; on desktop it lives at the top. The toggle button animates smoothly and swaps icons depending on screen size.
- **Standalone or Embedded** – Designed to run independently via `uvicorn` or as a sub‑mounted router inside a FastAPI superproject (e.g., Cutaway).

## Theme

Markbin uses a custom **“Sakura‑Vader”** dark theme. The colour palette (`#222222` background, `#e06c75` accent) keeps the interface quiet and focused. Distractions like toolbars are hidden until you need them.

## Technology Stack

| Layer          | Libraries / Tools                                                                          |
|----------------|--------------------------------------------------------------------------------------------|
| Editor & View  |[Vditor](https://github.com/Vanessa219/vditor) (IR mode, dark theme, native preview)       |
| Backend        | [FastAPI](https://fastapi.tiangolo.com/), [Motor](https://motor.readthedocs.io/) (async MongoDB) |
| Database       | MongoDB (collection `markbins.docs`)                                                       |
| Frontend       | Vanilla JavaScript, [Bootstrap Icons](https://icons.getbootstrap.com/)                     |
| Templating     | Jinja2 (via FastAPI)                                                                       |

## API Endpoints

All endpoints are prefixed with `/markbin` (configurable in the FastAPI router).

| Method | Path               | Description                                                                                   |
|--------|--------------------|-----------------------------------------------------------------------------------------------|
| `GET`  | `/`                | Edit mode – empty editor with draft restoration.                                              |
| `GET`  | `/{uuid}`          | View mode – renders the stored Markdown document with exact visual parity.                    |
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

File Structure
```
markbin/
├── markbin.py          # FastAPI router, endpoints, MongoDB connection
├── main.py             # Standalone entry point
├── markbin.html        # Jinja2 template, static asset links
├── static/
│   ├── style.css       # Sakura‑Vader theme, responsive layout, Vditor overrides
│   └── favicon.png
├── scripts/
│   └── app.js          # Editor initialisation, TOC, drag & drop logic, UI state
└── README.md
```

