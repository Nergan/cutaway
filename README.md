---
title: Nargan
emoji: 🧩
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# 🧩 Nargan's Pet‑Projects

A collection of small, standalone web applications and experiments built with **FastAPI** – a **Composable Modular Monolith** where every sub‑project is fully independent, yet they can be served together through a central meta‑application.

> **Zero tight coupling.** Any folder can be ripped out and run on its own, with its own routing, assets, dependencies, and even a dedicated Dockerfile.

---

## 🏛️ Architectural Design

This ecosystem follows a **Composable Modular Monolith** architecture. All projects live in a single repository and can be exposed via a unified FastAPI app, but there is **no hard dependency** between them. Each sub‑project is a bounded context:

- Own FastAPI router (or static files)
- Own templates / static assets
- Own isolated dependency list (e.g., `requirements.txt`)
- Own optional `Dockerfile`

<img src="https://sun9-49.userapi.com/s/v1/ig2/Z2vsZ9d9sN74a7iZNBxKXXwjq8pCGJueQ7uv8WIWRRsZ-yK4BZ_cbTW7zpQl4IrjdY793mU28AWTN9TA4wXdVjn1.jpg?quality=95&as=32x16,48x25,72x37,108x55,160x82,240x123,360x184,480x245,540x276,640x327,720x368,1080x552,1280x654&from=bu&u=0AP5UdsHBgGZbKWF46A54Ar9qTbbGI6wIJkpW778NqQ&cs=1280x0" alt="Architecture" style="display: block; margin: 0 auto;">

This gives you the best of both worlds: **monorepo convenience** with **microservice‑like flexibility**.

---

## 🚀 Subprojects

| Name | Endpoint | Description |
|------|----------|-------------|
| **Evenfest** | `/evenfest` | Cosplay & photographer community website with interactive drag‑and‑drop sidebar, dynamic MongoDB content. |
| **Formular** | `/formular` | Universal file converter (magic‑byte detection, FFmpeg, LibreOffice, Playwright, Pandoc). |
| **Foundry Blank Viewer** | `/foundry` | Nature‑themed client‑side viewer for Foundry VTT character JSON exports. |
| **Kanban** | `/kanban` | Minimalist local‑storage Kanban board with infinite sub‑project nesting and JSON import/export. |
| **Markbin** | `/markbin` | Secure Markdown sharing with Obsidian‑like live preview, TOC generation, and edit/view parity. |
| **Simple AI Chat** | `/simple-aichat` (disabled in main) | WebSocket chat interface for local GGUF models (llama.cpp), context memory, persona adaptability. |
| **Snake** | `/snake` | Classic Snake game reimagined with neon aesthetics, particle physics, and canvas animations. |
| **Toadbin** | `/toadbin` | Pastebin‑style code sharing with syntax highlighting, smart hotkeys (Ctrl+S, tabbing), cozy animated background. |
| **Yellow Mirror** | `/yellow-mirror` | Experimental proxy that streams external websites via WebRTC + headless browser engine. |

---

## 🛠️ Tech Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn
- **Database:** MongoDB (used by evenfest, toadbin, markbin, visitor counter)
- **Frontend:** HTML, CSS, JavaScript, Bootstrap, Vditor, highlight.js, custom fonts
- **Conversion engines:** FFmpeg, LibreOffice, Playwright, Pandoc (for Formular)
- **Deployment:** Docker (via `sdk: docker`), Vercel (via `vercel.json`), or standalone Uvicorn

---

## 📁 Project Structure

```
.
├── main.py                    # Main FastAPI app that mounts all subprojects
├── index.html                 # Landing page with language detection + visitor counter
├── vercel.json                # Vercel deployment config
├── Dockerfile                 # Optional unified Docker build
├── evenfest/                  # Cosplay community (FastAPI + MongoDB)
├── snake/                     # Snake game (static + background API)
├── toadbin/                   # Code bin (FastAPI + MongoDB + background videos)
├── formular/                  # File converter (FastAPI + Playwright)
├── yellow_mirror/             # Web proxy (FastAPI + httpx)
├── foundry_blank_viewer/      # Foundry character viewer (static HTML)
├── markbin/                   # Markdown editor/sharing (FastAPI + MongoDB)
├── kanban/                    # Kanban board (static HTML + client‑side JS)
├── simple_aichat/             # AI chat (WebSocket, llama.cpp)
└── mainpage-backgrounds/      # MP4 videos for landing page background
```

---

## 🧪 Running Locally

```bash
# Install root dependencies (if any) and subproject dependencies manually,
# or use the root requirements.txt that aggregates them.

uvicorn main:app --reload
```

Each sub‑project can also be run in isolation – just `cd` into its folder and launch its own `app.py` or `main.py` (if present).