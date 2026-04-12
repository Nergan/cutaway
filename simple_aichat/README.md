# Simple AI Chat

A minimalist application designed for direct interactions with local neural network models (GGUF format). The project is optimized to run in two distinct environments: as a standalone desktop application via `Eel`, and as an integrated web service within the broader Nargan's Projects `FastAPI` ecosystem.

## Core Features
- **Local Inference Engine**: Powered internally by `llama-cpp-python`. Zero reliance on external API services, ensuring absolute privacy.
- **Smart Context Management**: Supports Drag & Drop of plain `.txt` history files directly onto the UI to restore previous conversations, automatically mapping user/AI roles via internal placeholders (`<username>`, `<ainame>`).
- **Memory Tracking**: A visual token counter built into the UI actively calculates sequence length to warn you of context-window limits.
- **Dual Runtime Support**: 
  - **Desktop App**: Runs as a local Chromium window using Python `Eel` (`main.py`).
  - **Web Service**: Fully integrated into FastAPI with an asynchronous WebSocket backend (`simple_aichat.py`) using thread-safe queues.

## Running in Standalone Mode (Desktop)
1. Install dependencies:
   ```bash
   pip install -r requirements.txt