# Nargan's Projects Ecosystem

[Читать на русском языке (README.ru.md)](README.ru.md)

A unified, resilient, and dynamically orchestrated web ecosystem containing a collection of independent web applications (plugins). Built on top of FastAPI, Python, and MongoDB, this monorepo acts as an application hub designed to easily scale, auto-discover new modules, and gracefully degrade in case of database or system issues.

---

## Architecture Overview

The ecosystem operates on a modular, monolithic architecture governed by a central coordinator:

1. **Dynamic Plugin Discovery (`main.py`):** On startup, the root coordinator scans local directories, automatically looks for valid routers inside each project folder (evaluating multiple fallback entry points like `main.py`, `[plugin_name].py`, or direct routers), and mounts both static assets and API paths underneath isolated prefixes.
2. **Resilient System Status (`/api/status`):** The landing page dynamically polls this endpoint. If any plugin fails to import, load its requirements, or validate its entry points, it is flagged as `offline` and automatically dimmed on the user's interface, allowing the rest of the application hub to run undisturbed.
3. **Optimized RAM-First Tracking (`/api/track`):** Centralized analytics track unique visitors via MongoDB. Database roundtrips are minimized through a local `LRUSet` cache, protecting the database under heavy traffic surges.
4. **Dual-Boot Deployment:** All primary plugins contain a standalone boot mechanism (`main.py` inside their folders) allowing developers to run them individually as a desktop application using Eel, or as a standalone web application via `--web`.

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
* **Description:** A WebSocket-based real-time browser stream bypassing client-side constraints.
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

2. Run the dynamic script to automatically resolve all core and individual application dependencies:
   ```bash
   chmod +x build.sh
   ./build.sh
   ```

3. Configure your environmental values in a `.env` file at the root:
   ```env
   MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/
   ```

4. Launch the application:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

The script will launch Uvicorn on port `7860`, specifically initializing with standard `asyncio` loops to bypass common SSL handshake timeout bottlenecks found under alternative loop runners.