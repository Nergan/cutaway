# 🧩 Nargan's Pet‑Projects

A collection of small, standalone web applications and experiments built with **FastAPI** and deployed on **Vercel**.  
The landing page (index.html) serves as a hub to navigate between them.

---

## 🚀 Subprojects

| Name | Description | Endpoint |
|------|-------------|----------|
| **evenfest** | Cosplay community website with dynamic content loaded from MongoDB. | `/evenfest` |
| **snake** | Classic Snake game with a nature‑themed, video‑background UI. | `/snake` |
| **toadbin** | Code‑sharing platform similar to katbin, with syntax highlighting and a random background. | `/toadbin` |
| **formular** | File converter (docx→pdf, html→pdf) – currently limited. | `/formular` |
| **yellow mirror** | Simple web proxy that enables browsing external sites through the app. | `/yellow-mirror` |
| **foundry blank viewer** | Upload a Foundry VTT actor JSON file and view character traits in a fantasy UI. | `/foundry` |
| **markbin** | Markdown editor with live preview, saving, and sharing capabilities. | `/markbin` |
| **kanban** | Minimal kanban board with drag & drop, export/import, and local storage. | `/kanban` |
| **simple aichat** | Chat interface with a local LLM (llama.cpp) via WebSocket. | `/simple-aichat` (disabled in main) |

---

## 🛠️ Tech Stack

- **Backend:** Python 3.10+, [FastAPI](https://fastapi.tiangolo.com/)
- **Database:** MongoDB (used by evenfest, toadbin, markbin, visitor counter)
- **Frontend:** HTML, CSS, JavaScript, Bootstrap, Vditor, highlight.js, various fonts
- **Deployment:** Vercel (via `vercel.json`), Uvicorn for local development

---

## 📁 Project Structure

```
.
├── main.py                # Main FastAPI app that mounts all subprojects
├── index.html             # Landing page with language detection and visitor counter
├── vercel.json            # Vercel deployment configuration
├── evenfest/              # Cosplay community (FastAPI + MongoDB)
├── snake/                 # Snake game (static files + API for backgrounds)
├── toadbin/               # Code bin (FastAPI + MongoDB, background videos)
├── formular/              # File converter (FastAPI + Playwright)
├── yellow_mirror/         # Web proxy (FastAPI + httpx)
├── foundry_blank_viewer/  # Foundry character viewer (static HTML)
├── markbin/               # Markdown editor/sharing (FastAPI + MongoDB)
├── kanban/                # Kanban board (static HTML, client‑side JS)
├── simple_aichat/         # AI chat (currently disabled in main.py)
└── mainpage-backgrounds/  # MP4 videos for the landing page background
```
