# Foundry VTT Character Viewer (Wildwood Edition)

A standalone web application that displays character sheets from **Foundry Virtual Tabletop** actor JSON exports. The viewer provides a nature‑inspired, readable interface for browsing core stats, features, spells, inventory, and biography – all without needing a live Foundry server.

## Features

- **Drag & Drop** or click to upload a `.json` actor file exported from Foundry VTT.
- **Clean, responsive layout** with a forest/parchment theme.
- **Tabbed navigation**:
  - Core Stats (AC, HP, Speed, ability scores)
  - Features & Traits (class features, feats, race traits, etc.)
  - Spellbook
  - Inventory (weapons, equipment, consumables)
  - Biography
- **Automatic formatting** of Foundry‑specific markup:
  - Dice rolls `[[/r 1d8]]` become highlighted inline.
  - UUID links `@UUID[...]{Display Name}` are converted to clean, readable text.
- **No server‑side processing** – your JSON file stays in the browser.
