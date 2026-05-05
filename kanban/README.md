# Kanban Board

A minimalist, drag‑and‑drop Kanban board served as a single‑page web application via FastAPI.  
All data persists in the browser’s `localStorage` – no backend storage required.

## Features

- **Three default columns** (Pending, In Progress, Released) – fully customisable.
- **Inline editing** of column names, project titles, and nested sub‑projects.
- **Drag & drop** to reorder projects within and across columns; also reorder columns.
- **Nested sub‑projects** with recursive tree structure.
- **Colour accents**: cycle through palette colours for projects.
- **Export / Import** board state as JSON (download, upload, drag‑and‑drop).
- **Keyboard shortcut**: `Ctrl+S` / `Cmd+S` to export instantly.
- **Mobile responsive** layout with touch‑friendly controls.

## Getting Started

### Prerequisites

- Python 3.7 or higher

### Installation

1. Clone or download the repository.
2. Navigate to the project directory containing `main.py`, `kanban.py` and `kanban.html`.
3. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Board

Launch the FastAPI server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open your browser to [http://localhost:8000](http://localhost:8000).

> ⚙️ **Note:** The project depends on the relative path between `kanban.py` and `kanban.html`. Keep both files in the same directory.

### Usage

- **Rename a column/project/sub‑project** – click on its text to edit inline; press `Enter` to confirm or `Escape` to cancel.
- **Add a column** – click the `+ Column` button in the header.
- **Add a project** – hover over the bottom of a column to reveal the `+ Add Project` button (desktop), or tap it on touch devices.
- **Add a sub‑project** – hover over a project to see `+ add subproject`, or tap it on touch devices. Sub‑projects can be nested further.
- **Delete** – hover over a column/project/sub‑project and click the `×` icon. Confirmation dialogs appear if children exist.
- **Change project colour** – click the `●` button that appears on hover.
- **Export** – use the `↓ Export JSON` button or press `Ctrl+S`/`Cmd+S`.
- **Import** – click `↑ Import JSON` or drag and drop a `.json` file onto the page.
- **Drag & drop** columns by their header, and projects by their card.

## Project Structure

```
.
├── main.py          # FastAPI app entry point
├── kanban.py        # APIRouter serving kanban.html
├── kanban.html      # The complete Kanban board (HTML + CSS + JS)
├── requirements.txt # Python dependencies
└── README.md        # This file
```

## How It Works

The board is entirely client‑side. The HTML file contains all the HTML, CSS, and vanilla JavaScript needed to manage and display the board. Data is stored in `localStorage` under the key `minimal_kanban_data`, so it survives page reloads but is local to the browser.

The FastAPI server simply delivers the static `kanban.html` file at the root (`/`). No API endpoints are needed for data persistence.