# D&D Tools

A streamlined FastAPI subproject designed for Dungeons & Dragons players and Game Masters. It provides two interactive, client-side tools: a **Druid Helper** for managing Wild Shape transformations, and a **Foundry VTT Character Viewer** for parsing and displaying actor data directly in the browser.

## ✨ Features

### 🌿 Druid Helper
- **Dynamic Bestiary:** Search, filter, and sort creatures using natural language queries. Supports partial matches, synonyms, and stat-based sorting. A short word such as «скорос» sorts by speed instead of searching for that exact string.
- **Wild Shape Tiers:** Level 2, 4, and 8 lists are calculated from challenge rating and swim or fly speed, so a flying creature cannot appear in an earlier tier.
- **Sources:** Each card names where the creature comes from: the 2014 System Reference Document, a published book, or Homebrew. SRD numbers follow that document (CC BY 4.0, Wizards of the Coast). The list stays one JSON file; tiers are not stored, because they can be derived.
- **Bilingual Interface:** Instant toggle between Russian and English UI/text.
- **Responsive Design:** Collapsible sidebar, masonry card layout, dark/light theme persistence, and optimized mobile overlay.

### 📜 Foundry VTT Character Viewer
- **Local JSON Parsing:** Drag-and-drop or upload `.json` actor files exported from Foundry VTT. The same reader accepts Foundry 0.8–9 (`data`), Foundry 10 through 14 (`system`), and dnd5e 1.x through 5.x, including activity-based items.
- **Sheet Rendering:** Core stats, saving throws, skills, spell slots, concentration, conditions, initiative, death saves, AC formula, features, a spellbook grouped by level, inventory, and biography.
- **Foundry Syntax Support:** Roll macros (`[[/r ...]]`) become buttons that roll in the browser. Inline references become their labels. Description HTML from the file is shown as text, not inserted as markup.

## 🏗 Project Structure
```console
dnd/
├── __init__.py # Package initializer
├── router.py # FastAPI APIRouter configuration
├── scripts/
│ ├── druid_query.js # Search words and wild-shape tiers
│ ├── druid_helper.js # Bestiary cards, filters, and UI state
│ ├── foundry_actor.js # Foundry 0.8–14 actor reader
│ └── foundry_blank_viewer.js # Sheet rendering and roll buttons
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