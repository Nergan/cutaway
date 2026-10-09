# Formular — Universal Content Forge

**Formular** is a robust web application for seamless document conversion. Deployed as a sub-project within a larger meta-platform architecture (via Hugging Face Spaces), it utilizes system-level engines and Dijkstra-based AI routing to string together intermediary formats, achieving high-fidelity "any-to-any" conversions automatically.

## Supported Conversion Matrix

Formular relies on file-content detection (via Magic Bytes), not file extensions, ensuring files are accurately identified and only valid target formats are provided to the user.

| Input Detected | Allowed Output Formats | Underlying Engine utilized |
| :--- | :--- | :--- |
| **DOCX** / **DOC** | `PDF`, `HTML`, `TXT`, `MD` | LibreOffice, Pandoc |
| **PPTX** | `PDF` | LibreOffice |
| **PDF** | `HTML`, `TXT`, `MD` | PyMuPDF, Pandoc |
| **HTML** | `PDF`, `MD`, `TXT` | Chromium print (local), LibreOffice, Pandoc |
| **Markdown (MD)** | `PDF`, `HTML`, `TXT` | Chromium print (local), LibreOffice, Pandoc |
| **TXT** | `PDF`, `HTML`, `MD` | LibreOffice, Pandoc |
| **RTF** | `PDF`, `HTML`, `TXT`, `MD` | LibreOffice, Pandoc |
| **ODT** | `PDF`, `HTML`, `TXT`, `MD` | LibreOffice, Pandoc |
| **EPUB** / **DJVU** | `PDF`, `HTML`, `TXT`, `MD` | Pandoc, DjVuLibre |
| **Data (JSON, YAML, TOML, XML)**| `JSON`, `YAML`, `TOML`, `XML`, `PDF`, `HTML`, `TXT`, `MD` | PyYAML, toml, xmltodict |
| **Images (JPG, PNG, WEBP, SVG)**| `JPG`, `PNG`, `WEBP`, `PDF` | Pillow, CairoSVG |
| **Media (MP4, MP3, WAV, GIF, WEBM)**| `MP4`, `WEBM`, `MP3`, `WAV`, `GIF` | FFmpeg |
| **Spreadsheets (CSV, XLSX)**| `CSV`, `PDF` | Pandas, LibreOffice |
| **Archives (ZIP, RAR, 7Z, TAR, GZ)**| `ZIP`, `7Z`, `TAR`, `GZ` | p7zip-full |

## API

The live HTTP API is REST under `/formular/api`. `GET /formular/api` returns the size limits and the route map.

| Method | Path | Role |
|---|---|---|
| `POST` | `/formular/api/files` | Upload one or more files (`multipart` field `files`). `201` with ids, detected format, and allowed targets |
| `GET` | `/formular/api/files/{id}` | Metadata for an uploaded file |
| `POST` | `/formular/api/files/{id}/conversions` | Convert. JSON body `{"to":"mp3"}`, optional `audio`, `video`, `ffmpeg`, `merge_id`, `merge_loop`. The response is the converted file |
| `GET` | `/formular/api/voices` | Speech voices |
| `GET` | `/formular/api/voices/{id}/sample` | A short WAV of that voice |

On the public Space a request body cannot exceed 32 MiB. `max_file_bytes` in `GET /formular/api` is the largest single file that still fits. A `413` names both sizes, for example `note.txt is 51.2 MiB. The maximum is 32.0 MiB.`

`POST /formular/api/upload` and `POST /formular/api/convert` are the same two operations, in the form the page already sends. The page keeps using them.

The Russian design notes for a later workspace API are in [`docs/05-api.md`](docs/05-api.md). That later shape is not what the server implements today.

## Planned Redesign

A conceptual redesign (shared workspace, background jobs, public API, AI operations) is documented in [`docs/`](docs/README.md) (in Russian). AI agents should start with [`AGENTS.md`](AGENTS.md). Speech to text and text to speech are already in the current interface.

## Technology Stack
- **Backend Environment:** FastAPI, Python 3.11, Docker (Debian Slim)
- **Conversion Engines:** LibreOffice (headless), Pandoc, PyMuPDF, FFmpeg, DjvuLibre, xmltodict.
- **Frontend UI:** Vanilla JavaScript, CSS3. Features global lasso-selection algorithms, bulk execution limits, and multi-file drag and drop arrays. Built to run fluidly at 100vh scaling.