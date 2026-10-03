# Каталог конвертаций и операций

Обозначения:
- **Приоритет:** P0 — паритет с текущим formular и ядро; P1 — следующая волна; P2 — позже; P3 — эксперимент.
- **Исполнитель:** Б — браузер, С — сервер.
- **(AI)** — операция использует модели (`04-ai.md`).

Лицензии указаны для движков. Политика — в `02-constraints.md`, раздел 5: CLI-инструменты с копилефтом отдельным процессом допустимы; копилефтные библиотеки в процессе formular — только с решением владельца. Всё перепроверять при реализации.

## 1. По доменам

### Документы
- DOCX/DOC/ODT/RTF/TXT/MD/HTML/EPUB ↔ PDF/DOCX/HTML/MD/TXT — С: LibreOffice (MPL-2.0), pandoc (GPL, CLI); Б: pandoc.wasm, mammoth (BSD-2) — P0.
- Markdown + reference.docx → DOCX со стилями (комбинация) — С: pandoc — P1.
- Typst → PDF — С/Б: typst (Apache-2.0) — P1. LaTeX → PDF через TeX — тяжело, P3; LaTeX → DOCX/HTML через pandoc — P2.
- Сравнение двух DOCX (комбинация) — С: LibreOffice — P2.
- Документ → Markdown/JSON со структурой (AI) — С: Docling (MIT) — P1.

### PDF
- Объединение, разделение, поворот, порядок и извлечение страниц — Б: живой форк pdf-lib (MIT); С: qpdf/pikepdf (Apache-2.0 / MPL-2.0) — P0.
- PDF → изображения постранично и изображения → PDF — Б: pdf.js (Apache-2.0); С: pypdfium2 (Apache/BSD), img2pdf (LGPL) — P0.
- Сжатие — С: pikepdf и пережатие изображений — P1 (Ghostscript — AGPL, не брать).
- OCR → PDF с текстовым слоем (AI) — С: OCRmyPDF (MPL-2.0) + Tesseract — P1.
- Заполнение форм из JSON/CSV (комбинация, в том числе по строкам CSV) — С: pdfcpu (Apache-2.0) или pypdf (BSD) — P1.
- Таблицы из PDF → CSV/XLSX — С: pdfplumber (MIT), camelot (MIT) — P1.
- PDF/A, цифровая подпись (pyHanko, MIT), скрытие данных (redaction) — P2.
- PDF → DOCX — P2: pdf2docx теперь под MIT, но не развивается и зависит от PyMuPDF (AGPL); оценить альтернативы.

### Электронные книги
- EPUB ↔ FB2 ↔ DOCX/HTML/MD — С: pandoc — P1.
- CBZ/CBR ↔ PDF/EPUB — С/Б — P1.
- DjVu → PDF — С: ddjvu (GPL, CLI) — P0, уже есть.
- MOBI/AZW3 — только Calibre (GPL, около 400 МБ, PDF-вывод через QtWebEngine) — P3.
- Аудиокнига из EPUB (AI-озвучка) — С — P3.

### Таблицы и структурированные данные
- CSV/TSV/XLSX/ODS/JSON/NDJSON/Parquet/SQLite/XML/YAML/TOML, HTML- и Markdown-таблицы в любую сторону — Б: SheetJS CE (Apache-2.0), DuckDB-WASM (MIT); С: DuckDB (MIT), pandas (BSD) — P0/P1.
- SQL-запрос по файлам: CSV, XLSX, JSON, Parquet, несколько файлов сразу — Б/С: DuckDB — P1. Запрос на естественном языке → SQL (AI) — С: небольшая LLM — P2.
- INI, .env, properties, plist, HCL — P2.
- Графики Vega-Lite → SVG/PNG — Б: Vega (BSD-3); С: vl-convert (BSD-3, без браузера) — P2.
- Вывод JSON Schema из данных, проверка JSON по схеме (комбинация) — P2.
- MessagePack, CBOR, BSON ↔ JSON — P2.

### Изображения
- JPG/PNG/WEBP/GIF/BMP/TIFF/ICO/AVIF/QOI в любую сторону — Б: нативный декодер браузера, jSquash (Apache-2.0); С: Pillow, libvips (LGPL) — P0.
- HEIC/HEIF → другие — Б: libheif-js (LGPL); С: pillow-heif (лицензии x265 и патенты HEVC — проверить) — P1.
- JPEG XL — Б: jSquash; С: libjxl (BSD) — P1.
- RAW камер (rawpy, MIT + LibRaw), PSD (psd-tools, MIT), DDS/TGA, EXR — P2.
- Изменение размера, кроп, поворот, фильтры, водяной знак — Б/С — P0.
- SVG → PNG/PDF — Б: canvas; С: CairoSVG (LGPL), resvg (MPL/Apache) — P0. Растр → SVG — С: vtracer (MIT), potrace (GPL, CLI) — P1.
- EXIF: просмотр и очистка — Б/С — P1. Набор favicon — P1. Оптимизация: oxipng (MIT), mozjpeg (BSD) — P1.
- Удаление фона, удаление объектов, глубина, колоризация, увеличение (AI) — Б/С — P1/P2.
- Подпись и alt-text (AI) — Б/С: Florence-2 — P1.

### Аудио
- MP3/WAV/OGG/OPUS/FLAC/M4A/AAC/AIFF в любую сторону — С: ffmpeg; Б: Mediabunny и WASM-кодеры — P0.
- Обрезка, затухание, склейка, смешивание, кроссфейд — P0/P1.
- Темп, реверберация, бас с живым превью — P0, уже есть.
- Нормализация громкости EBU R128 (`loudnorm`), обрезка тишины — С — P1.
- Волна и спектрограмма в картинку или видео (`showwavespic`, `showspectrumpic`) — С — P1.
- Нарезка по CUE (комбинация) — P2.
- Теги и обложки — С: ffmpeg (mutagen под GPL — не импортировать) — P1.
- Шумоподавление (AI) — С: `arnndn`, DeepFilterNet — P1.
- Разделение на стемы (AI) — С: Demucs — P2. Аудио → MIDI (AI) — Б/С: basic-pitch — P2.
- Распознавание речи и субтитры (AI) — Б/С — P1.

### Видео
- MP4/WEBM/MKV/MOV/AVI/GIF/APNG/анимированный WEBP в любую сторону — С: ffmpeg; Б: Mediabunny + WebCodecs, ffmpeg.wasm — P0.
- Обрезка, кроп, масштаб, поворот, скорость, реверс, удаление звука — P0, частично есть.
- Извлечь, заменить или смешать аудиодорожку (комбинация) — Б/С — P0.
- «Сжать до N МБ» с двухпроходным расчётом битрейта — С — P1.
- GIF с палитрой (`palettegen`/`paletteuse`) — Б/С — P1.
- Кадры → ZIP, раскадровка, контактный лист — С — P1.
- Изображения (+ аудио) → слайд-шоу (комбинация) — С — P1.
- Склейка видео, водяной знак, «картинка в картинке», мозаика (комбинации) — С — P1.
- Вшить или встроить субтитры (комбинация) — С: ffmpeg + libass, mkvtoolnix — P1.
- Вертикальное 9:16 с размытым фоном — P2. Стабилизация (`vidstab`, если есть в сборке ffmpeg) — P2. Детекция сцен и нарезка (PySceneDetect, BSD-3) — P2. HLS — P3.
- Автосубтитры и их перевод (AI) — С — P1/P2.

### Субтитры
- SRT/VTT/ASS/SSA/TTML/SBV/LRC в любую сторону, сдвиг, смена FPS — Б/С: pysubs2 (MIT) — P1.
- Синхронизация с аудио — ffsubsync (проверить лицензию) — P2.
- Двуязычные из двух файлов (комбинация) — P2.

### Шрифты
- TTF/OTF/WOFF/WOFF2 в любую сторону — С: fontTools (MIT) + brotli — P1.
- Подмножество глифов, образец шрифта в PNG/PDF (комбинация шрифт + текст) — P2.

### Архивы и образы дисков
- ZIP/7Z/TAR/GZ/BZ2/XZ/ZST в любую сторону — С: 7-Zip, libarchive — P0, частично есть. RAR — только распаковка (несвободный unrar).
- Архив как коллекция: распаковать в рабочее пространство, применить операцию к каждому элементу — P0.
- Создать архив из выделенного (комбинация) — Б/С — P0.
- Содержимое архива → JSON/TXT — P1. ISO/WIM/MSI/DMG — извлечение через 7-Zip — P2.

### 3D и CAD
- OBJ/STL/PLY/GLB/GLTF/OFF/3MF в любую сторону — Б: three.js (MIT); С: trimesh (MIT) — P1.
- FBX, DAE и другие на вход — Б: assimpjs (MIT); С: assimp (BSD) — P2.
- STEP → GLB/STL — С: cascadio (MIT + OCCT LGPL) — P2. DXF → SVG/PDF/PNG — С: ezdxf (MIT) — P2.
- OBJ + MTL + текстуры → GLB (комбинация) — P2.
- Упрощение и починка мешей — P2. Превью-рендер — Б: three.js — P2.
- Изображение → 3D, текст → 3D (AI) — P3.

### ГИС
- GeoJSON/KML/GPX/Shapefile/GeoPackage/CSV с координатами/WKT в любую сторону, перепроецирование — С: GDAL (MIT, около 200 МБ) или pyogrio + shapely — P2. Хорошо стыкуется с ascii_city, который импортирует GeoJSON.
- GPX + фото → геотеги (exiftool), GPX + видео → оверлей телеметрии (комбинации) — P3.

### Наука и медицина
- DICOM → PNG/JPG/MP4 с анонимизацией — С: pydicom (MIT) — P2.
- HDF5/NetCDF/MAT/NPY → CSV/Parquet/JSON — С: h5py (BSD), xarray (Apache-2.0), scipy (BSD) — P2.
- FITS → PNG — astropy (BSD-3); NIfTI — nibabel (MIT) — P3.

### Ноты и музыка
- MIDI ↔ MusicXML ↔ ABC — С: music21 (BSD-3) — P2.
- Рендер нот в SVG/PDF без браузера — С: Verovio (LGPL-3.0) — P2.
- MIDI → аудио — С: FluidSynth (LGPL) + пермиссивный SoundFont (проверить лицензию) — P2.

### Диаграммы как код
- DOT → SVG/PNG/PDF — С: Graphviz (EPL-2.0, CLI); Б: viz.js (MIT) — P1.
- Mermaid → SVG/PNG — Б: mermaid.js (MIT); С: mmdr (MIT, ранняя стадия) — P1. mermaid-cli требует headless-браузер — нельзя.
- D2 → SVG — С: d2 (MPL-2.0); PNG/PDF у D2 идёт через headless-браузер — нельзя — P2.
- PlantUML — Java; есть вариант jar под MIT — P3.
- Текст или скриншот → код диаграммы (AI) — P3.

### Код и текст
- Перекодировка текста (cp1251, koi8-r, utf-16 → utf-8), переводы строк — Б/С — P0 (особенно полезно для русских файлов).
- Подсветка синтаксиса → HTML/PNG/PDF — С: Pygments (BSD) — P1.
- Форматирование и минификация JS/CSS/HTML/JSON/XML/SQL — С: Node.js уже есть в образе — P2.
- Jupyter → HTML/MD/PY; в PDF — через HTML и WeasyPrint (BSD) — С: nbconvert (BSD) — P1.
- Base64, hex, хэши — Б — P1.
- Сравнение двух текстов (комбинация) → HTML/patch — Б/С — P1.
- Перевод кода между языками и объяснение кода (AI) — P3.

### Почта, календари, контакты
- EML → PDF/HTML/TXT с вложениями — С: stdlib `email` — P2.
- MBOX ↔ EML — P2. MSG → EML — P2 (extract-msg под GPL — искать альтернативу).
- ICS ↔ CSV/JSON — icalendar (BSD) — P2. VCF ↔ CSV — vobject (Apache-2.0) — P2.

### Исполняемые файлы и байткод
- Метаданные PE/ELF/Mach-O и строки — С: LIEF (Apache-2.0) — P2.
- Дизассемблирование — С: Capstone (BSD-3) — P3.
- Декомпиляция байткода (JAR, APK, .NET, pyc, wasm) — С — P2.
- Нативная декомпиляция и AI-доработка — С — P3 (`04-ai.md`, раздел 10).

### Игры и моддинг (близко к проектам владельца)
- Minecraft NBT ↔ SNBT/JSON — С: nbtlib (MIT) — P2.
- Схемы `.schem` / `.litematic` → JSON или 3D — P3 (litemapy под GPL — не импортировать).
- Unity-бандлы → текстуры и модели — С: UnityPy (MIT); аудио FMOD проприетарное — исключить — P3.
- DDS/VTF ↔ PNG — P2/P3.
- JSON актёра Foundry VTT → PDF-лист персонажа (переиспользовать логику проекта `dnd`) — P3.

### Кодирование, QR, шифрование
- Текст → QR — Б: генератор QR в JS (MIT); С: segno (BSD) — P1.
- Распознавание QR и штрихкодов на картинке — С: zxing-cpp (Apache-2.0); Б: zxing-js — P1. Пакетная генерация из CSV (комбинация) — P2.
- Шифрование и расшифровка файла паролем — Б: WebCrypto; С: cryptography — P2.

## 2. Операции с несколькими входами

Роли — в скобках.

| Входы | Операция | Приоритет |
|---|---|---|
| видео + аудио | заменить дорожку, смешать, добавить вторую (`video`, `audio`) | P0 |
| изображение + аудио | видео из картинки и звука, видео с волной | P0 |
| файлы любых типов (N) | архив | P0 |
| PDF (N) | объединение с закладками | P0 |
| изображения (N) | PDF, GIF или видео, коллаж, спрайт-лист | P1 |
| видео (N) / аудио (N) | склейка (с кроссфейдом для аудио) | P1 |
| видео + субтитры | вшить или встроить | P1 |
| видео или PDF + изображение | водяной знак, «картинка в картинке» | P1 |
| шаблон DOCX/ODT/PPTX + CSV/JSON/XLSX | документ на каждую строку (`template`, `data`) | P1 |
| PDF-форма + JSON/CSV | заполненные формы | P1 |
| текст + текст, DOCX + DOCX, изображение + изображение | сравнение | P1/P2 |
| Markdown + изображения | EPUB или DOCX | P2 |
| CSV (N) | объединение строк или соединение по ключу (DuckDB) | P2 |
| JSON + JSON Schema | отчёт о проверке | P2 |
| OBJ + MTL + текстуры | GLB | P2 |
| FLAC + CUE | треки | P2 |
| субтитры A + B | двуязычные | P2 |
| аудио + текст песни | LRC или караоке (AI, выравнивание) | P2 |
| GPX + фото / GPX + видео | геотеги / оверлей телеметрии | P3 |

## 3. «Трансформации» — где конвертация становится обработкой данных

- **Запросы:** SQL по таблицам, jq по JSON; на естественном языке (AI).
- **Извлечения:** таблицы из PDF, кадры и дорожки из видео, текст из чего угодно, метаданные, вложения из писем и документов.
- **Сборки:** объединения, склейки, коллажи, архивы, заполнение шаблонов.
- **Генерация:** QR, графики, диаграммы, озвучка, тестовые данные.
- **Анализ:** громкость, длительность, хэши, поиск дубликатов среди файлов рабочего пространства (перцептивный хэш для картинок), определение языка, отчёт о структуре файла.

## 4. Проблемные движки

- **Требуют headless-браузер (запрещено):** mermaid-cli, экспорт D2 в PNG/PDF, компаньоны Kroki, nbconvert `webpdf`, скриншоты сайтов. PDF-вывод Calibre (QtWebEngine) — под вопросом.
- **Требуют Java:** jadx, CFR, Vineflower, Ghidra, PlantUML, JPEXS, epubcheck. Подключать только после решения о JRE в образе.
- **Требуют GUI или X-сервер:** MuseScore, рендер OpenSCAD в PNG.
- **Тяжёлые:** Calibre (около 400 МБ), Blender (около 1 ГБ), GDAL (около 200 МБ), TeX, LilyPond. Добавлять, только если окупаются.
- **Лицензионно сложные:** AGPL (PyMuPDF, Ghostscript, mupdf.js, BabelDOC, актуальная версия argos-translate-files, gifski); GPL-библиотеки в процессе (mutagen, extract-msg, litemapy); несвободный unrar.
