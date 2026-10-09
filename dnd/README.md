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

## API

The hub serves the tools at `/dnd`. `GET /dnd/api` lists the query fields.

`GET /dnd/api/beasts?q=скорос&cat=all&lang=ru` returns the same creatures the bestiary page would show, in the same order. `q` is the search box. `cat` is `all`, `fam`, `lvl2`, `lvl4`, or `lvl8`. `lang` is `ru` or `en` and chooses which name, size, tags, and habitats are searched and which name breaks a tie. Each beast is the stored record plus `categories`.

## Project structure

```console
dnd/
├── main.py
├── bestiary.py
├── scripts/
│   ├── druid_query.js
│   ├── druid_helper.js
│   ├── foundry_actor.js
│   └── foundry_blank_viewer.js
├── static/
│   ├── db.json
│   └── styles/
└── templates/
    ├── menu.html
    ├── druid_helper.html
    └── foundry_blank_viewer.html
```

## Integration
This project is structured as a FastAPI `APIRouter` and is intended to be included in a larger FastAPI application.

1. **Mount the Router:** Import the router in your main FastAPI app and mount it under the `/dnd` prefix. Ensure your main app serves static files if you want to customize the asset pipeline, though the templates reference paths relative to the router.
2. **Run the Application:** Start your ASGI server (e.g., `uvicorn`) pointing to your main application file.
3. **Access the Hub:** Navigate to `/dnd/` in your browser to access the split-screen menu. The Druid Helper and Foundry Viewer are available at `/dnd/druid-helper` and `/dnd/foundry-blank-viewer` respectively.