---
title: Nargan
emoji: 🧩
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# 🧩 Nargan's Pet‑Projects

A collection of small, standalone web applications and experiments built with **FastAPI** – a **Resilient Plugin Monolith** where every sub‑project is fully independent, yet they dynamically compose a central meta‑application at runtime.

> **Zero hard dependencies. Graceful degradation.** Any folder can be ripped out and run on its own. If a project fails to build or crashes, the root application simply bypasses it and stays online.

---

## 🏛️ Architectural Design

This ecosystem transitioned from a statically linked monolith to a **Resilient Plugin Monolith**. All projects live in a single monorepo but are treated as plug-and-play modules without hardcoded imports. 

- **Two-Tier Dependency Management:** Core system dependencies (Tier 1) are isolated from sub-project dependencies (Tier 2). Build failures in a sub-project do not halt the entire Docker build.
- **Dynamic Orchestration:** The root FastAPI app auto-discovers folders, dynamically attempts to mount their routers, and safely catches any `ImportError` or initialization failure.
- **Strict Isolation:** Each sub-project is a bounded context with its own routing, assets, dependencies, and fallback `main.py` entrypoints for standalone desktop execution (via Eel) or web execution.

<img src="https://sun9-49.userapi.com/s/v1/ig2/Z2vsZ9d9sN74a7iZNBxKXXwjq8pCGJueQ7uv8WIWRRsZ-yK4BZ_cbTW7zpQl4IrjdY793mU28AWTN9TA4wXdVjn1.jpg?quality=95&as=32x16,48x25,72x37,108x55,160x82,240x123,360x184,480x245,540x276,640x327,720x368,1080x552,1280x654&from=bu&u=0AP5UdsHBgGZbKWF46A54Ar9qTbbGI6wIJkpW778NqQ&cs=1280x0" alt="Architecture" style="display: block; margin: 0 auto;">

---

## 🚀 Subprojects

| Name | Endpoint | Description |
|------|----------|-------------|
| **Evenfest** | `/evenfest` | Cosplay & photographer community website with interactive drag‑and‑drop sidebar, dynamic MongoDB content. |
| **Formular** | `/formular` | Universal file converter (magic‑byte detection, FFmpeg, LibreOffice, Playwright, Pandoc). |
| **D&D Tools** | `/dnd` | Utilities including a nature-themed client-side viewer for Foundry VTT JSON exports and a Druid helper. |
| **Kanban** | `/kanban` | Minimalist local‑storage Kanban board with infinite sub‑project nesting and JSON import/export. |
| **Markbin** | `/markbin` | Secure Markdown sharing with Obsidian‑like live preview, TOC generation, and edit/view parity. |
| **Snake** | `/snake` | Classic Snake game reimagined with neon aesthetics, particle physics, and canvas animations. |
| **Toadbin** | `/toadbin` | Pastebin‑style code sharing with syntax highlighting, smart hotkeys (Ctrl+S, tabbing), cozy animated background. |
| **Yellow Mirror** | `/yellow-mirror` | Experimental proxy that streams external websites via WebRTC + headless browser engine. |

---

## 🛠️ Tech Stack

- **Backend:** Python 3.11, FastAPI, Uvicorn, importlib (dynamic mounting)
- **Database:** MongoDB (used by evenfest, toadbin, markbin, visitor counter)
- **Frontend:** HTML, CSS, JavaScript, Bootstrap, Vditor, highlight.js, custom fonts
- **System Engines:** FFmpeg, LibreOffice, Playwright, Pandoc, libmagic
- **Deployment:** Docker (`sdk: docker`), auto-executed via custom `build.sh` and `start.sh`

---

## 📁 Project Structure

```
.
├── main.py                    # Root Orchestrator (Auto-discovers and mounts plugins)
├── build.sh                   # Resilient build script for two-tier dependency installation
├── start.sh                   # Process supervisor for uvicorn and background tasks
├── index.html                 # Landing page with language detection + visitor counter
├── Dockerfile                 # Unified system Docker build
├── requirements.txt           # Tier 1 (Core) dependencies
├── dnd/                       # D&D utilities (FastAPI + static HTML)
├── evenfest/                  # Cosplay community (FastAPI + MongoDB)
├── formular/                  # File converter (FastAPI + Playwright + Python Magic)
├── kanban/                    # Kanban board (static HTML + client‑side JS)
├── markbin/                   # Markdown editor/sharing (FastAPI + MongoDB)
├── snake/                     # Snake game (static + background API)
├── toadbin/                   # Code bin (FastAPI + MongoDB + background videos)
└── yellow_mirror/             # Web proxy (FastAPI + httpx)
```

---

## 🧪 Running Locally

```bash
# 1. Install core dependencies
pip install -r requirements.txt

# 2. Run the dynamic orchestrator
uvicorn main:app --reload

# 3. Check system status (Which plugins successfully mounted?)
curl http://127.0.0.1:8000/api/status
```

Each sub‑project can also be run in total isolation – just `cd` into its folder and launch its dual-boot `main.py` to open either the web server or the Eel-powered desktop application!