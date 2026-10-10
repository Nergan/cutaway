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

Some directories exist only in the GitHub monorepo for local work and CI. They are not built, started, or published on this Space.

---

## Ecosystem Directory

### 🚀 Root Hub

* **landing (`index.html`, `main.py`):** A directory of the projects. It follows the browser language, shows the visitor count, leaves out a project the active profile does not run, dims a project the hub reports as offline, and plays a random background video. `GET /api` returns that same page as JSON: the title, the welcome line in English and Russian, the GitHub and Telegram links, the visitor count, and the project cards.

### 📁 Application Registry

#### 1. [Formular](./formular/) (Document & Media Forge)

* **Description:** An all-to-all file converter utilizing a programmatic pathfinding routing engine based on Dijkstra's algorithm.
* **Key Integrations:** LibreOffice, Pandoc, PyMuPDF, FFmpeg, Pandas, Pillow, CairoSVG, and 7-Zip. HTML-to-PDF uses the same local document engines as the other office formats.
* **Core Capabilities:** Interlinks disparate media categories together (e.g., Markdown ➔ HTML ➔ PDF, or Excel ➔ CSV ➔ JSON ➔ XML) dynamically compiling an execution chain for any supported atomic hop.

#### 2. [Toadcode](./toadcode/) (Collaborative Workspace)

* **Description:** A collaborative, virtual file system environment providing temporary online project spaces.
* **Core Capabilities:** Supports direct folder structures, multiple-file uploading, direct `.ZIP` unpacking, and GitHub URL proxy ingestion. Includes text selection lassoing, manual line-number rendering, standard auto-completion, and real-time project size limits (10MB).

#### 3. [Markbin](./markbin/) (Markdown Editor & Shared Bin)

* **Description:** A Markdown rendering, viewing, and sharing workspace powered by the Vditor engine.
* **Core Capabilities:** Interactive visual editing, custom auto-generating tables of contents, client-side downloading, and self-destructing links. Incorporates MongoDB-backed TTL indexes, managing automatic document deletion when specified expiration timestamps are reached. `POST /markbin/api/docs` stores a document and `GET /markbin/api/docs/{id}` reads it back. The page still saves through `POST /markbin/api/save`.

#### 4. [Kanban](./kanban/) (Lite Board Organizer)

* **Description:** A minimalist task manager utilizing recursive nested lists and a drag-and-drop hierarchy.
* **Core Capabilities:** Infinite recursive task nests, native file picker exports, drag-and-drop polyfills for touchscreens, keyboard shortcuts, and customizable color-coding.

#### 5. [D&D Tools](./dnd/) (Game Master Utilities)

* **Description:** Utilities for the 2014 wild-shape rules. `GET /dnd/api/beasts` answers the same search the page does.
* **Core Capabilities:**
  * **Bestiary & Wild Shape Helper:** Search, filters, exclusion tags (`-`), and stat sorting, including a short word such as a stem of “speed”. Each card names its source. Wild-shape tiers are calculated from challenge rating and movement.
  * **Foundry VTT Character Viewer:** Reads an actor export from Foundry 0.8 through 14 in the browser. Roll expressions become buttons. Description markup is shown as text.

#### 6. [Evenfest](./evenfest/) (Cosplay Community Website)

* **Description:** A template-driven website configured via MongoDB, using Jinja2 layouts for community news, photographers, tickets, and rules. `GET /evenfest/api/pages` lists those pages, and `GET /evenfest/api/pages/{id}` returns the text the page shows.

#### 7. [Snake](./snake/) (Organic Arcade)

* **Description:** An organic, canvas-based arcade game utilizing vector particle calculations, dynamic difficulty scaling, and a selection API serving video backgrounds.

#### 8. [Soon](./soon/) (Shared Canvas)

* **Description:** An unauthenticated collaborative board. Everyone in the same room draws on one canvas; there is no landing-page card, the route is `/soon`.
* **Core Capabilities:** Live strokes and named cursors over WebSocket, image paste/drag-and-drop stored on Cloudinary with hash dedup, a collapsible sidebar, and jump-to-user edge hints. One shared room at `/soon`.

#### 9. [ASCII City](./ascii_city/) (Multiplayer ASCII Cityscape)

* **Description:** A first-person cyberpunk city rendered entirely as glowing ASCII, walked by everyone who opens the page. The district is generated procedurally from a seed and every position in it belongs to the server.
* **Core Capabilities:** Authoritative 20 Hz simulation with client-side prediction and reconciliation, a ten-byte-per-player binary WebSocket protocol, interest management, proximity and district chat. A WebGL2 raycaster draws the character grid in one instanced call against a glyph atlas that carries its own neon bleed, with a Canvas2D fallback and adaptive quality. Binary 256 m tiles are decoded in a Web Worker and cached in MongoDB; a second implementation of the world port imports tagged GeoJSON from OpenStreetMap into the identical tile format.

#### 10. [Mods](./minecraft_mods/) (Minecraft mod list)

* **Description:** A catalog of Minecraft mods whose GitHub repositories end with `mod`. The route is `/mods`.
* **Core Capabilities:** Reads the public GitHub account, shows each mod's summary, license, GitHub and Modrinth links, the mod jar from the latest release, and the companion jars from that release. `GET /mods/api/mods` returns those cards, and `q`, `loader`, `minecraft`, and `license` narrow the list. `MODRINTH_TOKEN` marks projects that are still in review.

---

## Deployment & Setup

The repository is structured to run seamlessly on Hugging Face Spaces (using continuous syncing workflows), Vercel deployments, or standalone local servers.

### System Prerequisites

Ensure the following host engines are installed for full conversion capabilities:

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