# D&D Tools

A streamlined FastAPI subproject designed for Dungeons & Dragons players and Game Masters. It provides two interactive, client-side tools: a **Druid Helper** for managing Wild Shape transformations, and a **Foundry VTT Character Viewer** for parsing and displaying actor data directly in the browser.

## ✨ Features

### 🌿 Druid Helper
- **Dynamic Bestiary:** Search, filter, and sort creatures using natural language queries. Supports partial matches, synonyms, and stat-based sorting.
- **Wild Shape Tiers:** Creatures are automatically categorized by Druid level (Lvl 2, 4, 8) with movement type restrictions (Land, Swim, Fly).
- **Bilingual Interface:** Instant toggle between Russian and English UI/text.
- **Responsive Design:** Collapsible sidebar, masonry card layout, dark/light theme persistence, and optimized mobile overlay.

### 📜 Foundry VTT Character Viewer
- **Local JSON Parsing:** Drag-and-drop or upload `.json` actor files exported from Foundry VTT.
- **Complete Sheet Rendering:** Automatically parses and displays Core Stats, Features & Traits, Spellbooks, Inventory, and Biography.
- **Foundry Syntax Support:** Renders Foundry's custom markdown, roll macros (`[[/r ...]]`), and inline references into clean, readable HTML.

## 🏗 Project Structure
```console
dnd/
├── __init__.py # Package initializer
├── router.py # FastAPI APIRouter configuration
├── scripts/
│ ├── druid_helper.js # Bestiary logic, search, filter, sorting & UI state
│ └── foundry_blank_viewer.js # JSON parsing, Foundry macro processing & tab rendering
├── static/
│ └── db.json # Static creature database (CR, stats, tags, habitats)
├── styles/
│ ├── druid_helper.css # Druid helper theming & responsive layout
│ ├── foundry_blank_viewer.css # Character sheet styling & animations
│ └── menu.css # Landing page split-screen & video background
└── templates/
├── druid_helper.html # Druid Helper entry point
├── foundry_blank_viewer.html # Foundry Viewer entry point
└── menu.html # Hub landing page
```


## 🔌 Integration & Usage
This project is structured as a FastAPI `APIRouter` and is intended to be included in a larger FastAPI application.

1. **Mount the Router:** Import the router in your main FastAPI app and mount it under the `/dnd` prefix. Ensure your main app serves static files if you want to customize the asset pipeline, though the templates reference paths relative to the router.
2. **Run the Application:** Start your ASGI server (e.g., `uvicorn`) pointing to your main application file.
3. **Access the Hub:** Navigate to `/dnd/` in your browser to access the split-screen menu. The Druid Helper and Foundry Viewer are available at `/dnd/druid-helper` and `/dnd/foundry-blank-viewer` respectively.