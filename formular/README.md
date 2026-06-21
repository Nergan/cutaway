# Formular — Universal Content Forge

**Formular** is a robust web application for seamless document conversion. Deployed as a sub-project within a larger meta-platform architecture (via Hugging Face Spaces), it utilizes system-level engines and Dijkstra-based AI routing to string together intermediary formats, achieving high-fidelity "any-to-any" conversions automatically.

## Supported Conversion Matrix

Formular relies on file-content detection (via Magic Bytes), not file extensions, ensuring files are accurately identified and only valid target formats are provided to the user.

| Input Detected | Allowed Output Formats | Underlying Engine utilized |
| :--- | :--- | :--- |
| **DOCX** / **DOC** | `PDF`, `HTML`, `TXT`, `MD` | LibreOffice, Pandoc |
| **PPTX** | `PDF` | LibreOffice |
| **PDF** | `HTML`, `TXT`, `MD` | PyMuPDF, Pandoc |
| **HTML** | `PDF`, `MD`, `TXT` | Playwright (Chromium), Pandoc |
| **Markdown (MD)** | `PDF`, `HTML`, `TXT` | Playwright, Pandoc |
| **TXT** | `PDF`, `HTML`, `MD` | LibreOffice, Pandoc |
| **RTF** | `PDF`, `HTML`, `TXT`, `MD` | LibreOffice, Pandoc |
| **ODT** | `PDF`, `HTML`, `TXT`, `MD` | LibreOffice, Pandoc |
| **EPUB** / **DJVU** | `PDF`, `HTML`, `TXT`, `MD` | Pandoc, DjVuLibre |
| **Data (JSON, YAML, TOML, XML)**| `JSON`, `YAML`, `TOML`, `XML`, `PDF`, `HTML`, `TXT`, `MD` | PyYAML, toml, xmltodict |
| **Images (JPG, PNG, WEBP, SVG)**| `JPG`, `PNG`, `WEBP`, `PDF` | Pillow, CairoSVG |
| **Media (MP4, MP3, WAV, GIF, WEBM)**| `MP4`, `WEBM`, `MP3`, `WAV`, `GIF` | FFmpeg |
| **Spreadsheets (CSV, XLSX)**| `CSV`, `PDF` | Pandas, LibreOffice |
| **Archives (ZIP, RAR, 7Z, TAR, GZ)**| `ZIP`, `7Z`, `TAR`, `GZ` | p7zip-full |

## Technology Stack
- **Backend Environment:** FastAPI, Python 3.11, Docker (Debian Slim)
- **Conversion Engines:** LibreOffice (headless), Playwright, Pandoc, PyMuPDF, FFmpeg, DjvuLibre, xmltodict.
- **Frontend UI:** Vanilla JavaScript, CSS3. Features global lasso-selection algorithms, bulk execution limits, and multi-file drag and drop arrays. Built to run fluidly at 100vh scaling.