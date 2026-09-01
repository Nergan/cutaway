---
title: Nargan
emoji: 🫠
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Nargan's Projects Ecosystem

[Читать на русском языке (README.ru.md)](README.ru.md)

A unified, resilient web ecosystem containing a collection of independent web applications. Built on FastAPI, Python, and MongoDB, the monorepo uses an explicit project registry, hosting profiles, runtime quotas, and optional process isolation.

---

## Architecture Overview

The ecosystem is governed by the manifest in `orchestrator.toml`:

1. **Explicit Registry:** Only declared projects can be built, deployed, or run. A project-local `.project-ignore` is a fail-closed kill switch.
2. **Process Isolation:** The Hugging Face profile runs one lazy uvicorn worker per project. The hub only proxies HTTP/WebSocket traffic, so a worker crash does not import into or stop neighbouring projects.
3. **Resource Policies:** Per-project traffic, concurrency, timeout, memory, CPU, subprocess, connection, temporary-disk, restart, and circuit-breaker limits are enforced by the hub and supervisor.
4. **Compatible Embedded Mode:** `CUTAWAY_ISOLATION=embedded` retains an in-process mode for local or constrained infrastructure.
5. **Runtime Status:** `/healthz` reports hub health and `/api/status` reports disabled, starting, online, degraded, and circuit-open projects.

See [the orchestrator guide](docs/orchestrator.md) for configuration and operational limits.

---

## Ecosystem Directory

### 🚀 Root Hub

* **landing (`index.html`, `main.py`):** A custom directory dashboard that translates across languages, tracks visitor counts, dynamically dims offline projects, and loads random ambient background videos.

### 📁 Application Registry

#### 1. [Formular](./formular/) (Document & Media Forge)

* **Description:** An all-to-all file converter utilizing a programmatic pathfinding routing engine based on Dijkstra's algorithm.
* **Key Integrations:** Headless Playwright (HTML to PDF rendering), PyMuPDF, LibreOffice, FFmpeg, Pandoc, Pandas, Pillow, CairoSVG, and 7-Zip.
* **Core Capabilities:** Interlinks disparate media categories together (e.g., Markdown ➔ HTML ➔ PDF, or Excel ➔ CSV ➔ JSON ➔ XML) dynamically compiling an execution chain for any supported atomic hop.

#### 2. [Yellow Mirror](./yellow_mirror/) (Headless Remote Mirror)

* **Description:** A WebSocket-based real-time browser stream for trusted, explicitly allowlisted destinations. It is disabled in the Hugging Face profile.
* **Core Capabilities:** Spins up persistent isolated Chromium contexts within server-side Playwright. Employs CDP Screencast protocols, compressing rendering frames as base64 JPEG sequences sent via high-speed WebSockets directly to an HTML5 canvas. Forwards raw mouse movements, clicks, and multi-language keyboard layouts.

#### 3. [Toadcode](./toadcode/) (Collaborative Workspace)

* **Description:** A collaborative, virtual file system environment providing temporary online project spaces.
* **Core Capabilities:** Supports direct folder structures, multiple-file uploading, direct `.ZIP` unpacking, and GitHub URL proxy ingestion. Includes text selection lassoing, manual line-number rendering, standard auto-completion, and real-time project size limits (10MB).

#### 4. [Markbin](./markbin/) (Markdown Editor & Shared Bin)

* **Description:** A Markdown rendering, viewing, and sharing workspace powered by the Vditor engine.
* **Core Capabilities:** Interactive visual editing, custom auto-generating tables of contents, client-side downloading, and self-destructing links. Incorporates MongoDB-backed TTL indexes, managing automatic document deletion when specified expiration timestamps are reached.

#### 5. [Kanban](./kanban/) (Lite Board Organizer)

* **Description:** A minimalist task manager utilizing recursive nested lists and a drag-and-drop hierarchy.
* **Core Capabilities:** Infinite recursive task nests, native file picker exports, drag-and-drop polyfills for touchscreens, keyboard shortcuts, and customizable color-coding.

#### 6. [D&D Tools](./dnd/) (Game Master Utilities)

* **Description:** Utilities for Dungeons & Dragons 5th Edition (2024 ruleset).
* **Core Capabilities:**
  * **Bestiary & Wild Shape Helper:** A searchable and filterable database supporting synonym matching, exclusion tags (`-`), language toggle, and complex multi-variable normalized sorting.
  * **Foundry VTT Character Viewer:** An actor `.json` import pipeline rendering character sheets natively on the web. Parses Roll expressions and dynamic rich-text references.

#### 7. [Evenfest](./evenfest/) (Cosplay Community Website)

* **Description:** A template-driven website configured directly via MongoDB backends, using Jinja2 layouts to dynamically output community news, photographers, tickets, and rules.

#### 8. [Snake](./snake/) (Organic Arcade)

* **Description:** An organic, canvas-based arcade game utilizing vector particle calculations, dynamic difficulty scaling, and a selection API serving video backgrounds.

#### 9. [Soon](./soon/) (Shared Canvas)

* **Description:** An unauthenticated collaborative board. Everyone in the same room draws on one canvas; there is no landing-page card, the route is `/soon`.
* **Core Capabilities:** Live strokes and named cursors over WebSocket, image paste/drag-and-drop stored on Cloudinary with hash dedup, a collapsible sidebar, and jump-to-user edge hints. One shared room at `/soon`.

---

## Deployment & Setup

The repository is structured to run seamlessly on Hugging Face Spaces (using continuous syncing workflows), Vercel deployments, or standalone local servers.

### System Prerequisites

Ensure the following host engines are installed for full conversion/mirroring capabilities:

* Python 3.10+
* MongoDB
* LibreOffice (Headless CLI)
* FFmpeg & FFprobe
* 7-Zip (`7z`)
* CairoSVG dependencies

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Nergan/projects.git
   cd projects
   ```

2. Build the projects enabled by the selected hosting profile:

   ```bash
   chmod +x build.sh
   CUTAWAY_PROFILE=local ./build.sh
   ```

3. Configure your environmental values in a `.env` file at the root:

   ```env
   MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/
   ```

4. Launch the application (`embedded` is the local profile default):

   ```bash
   chmod +x start.sh
   ./start.sh
   ```

The script will launch Uvicorn on port `7860`, specifically initializing with standard `asyncio` loops to bypass common SSL handshake timeout bottlenecks found under alternative loop runners.