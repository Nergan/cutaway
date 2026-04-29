# Markbin

Markbin is a minimalist, fast, and secure Markdown sharing service, acting as a "Pastebin for Markdown". It features a powerful Obsidian-like Live Preview editor, dynamically generating Table of Contents (TOC), and secure database storage.

## Features
- **Obsidian-like Live Preview**: Integrated with `Vditor`, Markdown syntax hides and renders instantly in edit mode.
- **Dynamic Document Structure (TOC)**: Automatically extracts headers (stripping HTML and formatting) to create a clickable sidebar hierarchy.
- **Multiple Upload Methods**: Supports typing directly, drag & dropping `.md` or `.txt` files, and clicking to open a file selection dialog.
- **Secure Read Mode**: Utilizes `marked.js` and `DOMPurify` to safely render Markdown while sanitizing malicious scripts/HTML payloads.
- **Custom Hotkeys & UI**: Intercepts `Ctrl+S` (or `Cmd+S`) to save snippets natively with animation instead of triggering the browser save dialog. Contains an elegant sliding bottom navigation bar.
- **Standalone or Integrated**: Built to run entirely on its own via `uvicorn` or to act as a sub-mounted router within a FastAPI superproject (e.g., Cutaway).

## Theme
Markbin utilizes a custom "Sakura-Vader" dark theme. The layout prioritizes content over UI noise, keeping distractions hidden until needed.

## API Structure
GET / - Opens the Live Preview editor interface.
GET /{uuid} - Opens a previously saved Markdown document in Read-Only mode.
POST /api/save - Generates an 8-character UUID, saves the raw Markdown payload to MongoDB, and returns the UUID.
GET /api/docs/{uuid} - Fetches the raw Markdown content for a specific UUID.