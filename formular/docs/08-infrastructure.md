# Изменения инфраструктуры

Конкретные правки манифеста, супервизора, образа, тестов и CI, без которых новая архитектура не заработает. Все правки затрагивают общую экосистему, поэтому вносить их маленькими шагами и после каждого проверять соседей (раздел 7).

## 1. `orchestrator.toml`

Предлагаемые значения — отправная точка. Сумму `memory_mb` всех проектов профиля `hf` держать ниже `global_memory_budget_mb` (12288) с запасом на хаб.

```toml
[projects.formular]
env_allowlist = [
  "FORMULAR_MAX_UPLOAD_BYTES", "FORMULAR_MAX_OUTPUT_BYTES", "FORMULAR_SESSION_TTL_SECONDS",
  "FORMULAR_MAX_CONCURRENT_JOBS", "FORMULAR_MAX_ARCHIVE_FILES", "FORMULAR_MAX_ARCHIVE_UNPACKED_BYTES",
  # новые
  "FORMULAR_WORKSPACE_TTL_SECONDS", "FORMULAR_JOB_DISK_MB", "FORMULAR_MODEL_CACHE_MB",
  "MONGODB_URI", "MONGO_MAX_POOL_SIZE", "MONGO_TLS", "MONGO_TLS_ALLOW_INVALID_CERTS",
]

[projects.formular.network]
# Модели и поиск моделей — хосты Hugging Face (скачивание идёт через поддомены hf.co).
# Cloudinary не добавлять: зеркала нет (решение D13).
allowed_hosts = ["huggingface.co", "*.huggingface.co", "*.hf.co"]
allow_private = false
requests_per_minute = 600

[profiles.hf.projects.formular.env_defaults]
FORMULAR_WORKSPACE_TTL_SECONDS = "86400"   # решение D4: не больше суток
FORMULAR_MAX_CONCURRENT_JOBS = "1"
FORMULAR_JOB_DISK_MB = "4096"
FORMULAR_MODEL_CACHE_MB = "8192"
MONGO_MAX_POOL_SIZE = "3"
MONGO_TLS_ALLOW_INVALID_CERTS = "0"

[profiles.hf.projects.formular.limits]
max_concurrency = 6              # короткие запросы параллельно; тяжёлые задачи ограничивает сам formular
queue_timeout_seconds = 5
memory_mb = 5120                 # проверить сумму с соседями
temp_mb = 14336                  # модели + файлы задач; formular держит свои подбюджеты
fsize_mb = 8192                  # веса моделей и большие результаты
nofile = 1024
traffic_bytes_per_minute = 536870912
request_bytes = 33554432         # оставить; большие файлы — кусками
response_bytes = 134217728       # оставить; скачивание больших файлов — по Range
```

Пояснения:
- `max_concurrency = 6` исправляет 503 на все запросы во время одной конвертации (`01-current-state.md`, P5). В живом профиле hf это уже стоит вместе с `heavy_jobs = 1`: короткие запросы идут параллельно, тяжёлый слот остаётся один. Числа памяти и диска в примере выше пока не применены.
- Сеть: у formular на hf включён `enforce_allowlist`. Супервизор поднимает локальный выход и пускает только перечисленные хосты. Пустой список по-прежнему глушится. Formular дополнительно проверяет каждый свой адрес через `shared_network.validate_outbound_url` и не ходит по адресам от пользователя.
- `FORMULAR_HF_TOKEN` не добавлять (решение D14). Это был бы read-токен владельца только для более высоких лимитов Hub API, а не ключ публичного API formular. Лимиты за 5 минут (API / скачивание / страницы): анонимно — 500 / 3000 / 100 на IP. Ответы поиска кэшировать. Секрет на legacy-Space не заводить.

## 2. Супервизор и `shared_runtime`

### 2.1. Фоновые задачи и idle timeout
`ProjectSupervisor._inspect_worker` останавливает worker, если `last_request` старше `idle_timeout_seconds` и файл `<runtime_dir>/busy` не обновлялся последние 90 секунд. Путь передаётся воркеру как `CUTAWAY_BUSY_FILE`. Пока конвертация идёт внутри запроса, formular обновляет маркер каждые 20 секунд.

Очереди, которая живёт после закрытия вкладки, ещё нет. Когда она появится, тот же маркер нужно обновлять, пока есть задачи `queued` или `running`. Вариант `idle_timeout_seconds = 0` не используется: worker по-прежнему засыпает без работы.

### 2.2. CPU
Сейчас дерево процессов formular больше 30 секунд выше 180% убивается. Это защищает соседей, но убивает любую долгую работу. Нужно сразу два изменения.

- **Низкий приоритет для тяжёлых процессов.** Сделано: `shared_runtime.run_process(..., background=True)` на posix вызывает `os.nice(19)` в дочернем процессе. Formular передаёт этот флаг своим внешним движкам. Класс `SCHED_IDLE` не используется.
- **Политика CPU в супервизоре:** ещё не менялась.
  - либо опция проекта (например, `cpu_enforcement = "observe"` или `cpu_exempt_background = true`), при которой превышение CPU не убивает worker, если тяжёлые процессы работают с низким приоритетом;
  - либо поднять `cpu_percent` выше достижимого на 2 vCPU и `cpu_grace_seconds` до нескольких минут.

  Лимиты памяти, процессов и диска остаются строгими.

Дополнительно, как защита в глубину, — ограничение потоков в самом formular:
- ffmpeg: `-threads 2`, а для libvpx — без `-threads 4`;
- ONNX Runtime и OpenMP: 1–2 потока;
- llama.cpp: `-t 2`;
- LibreOffice работает в один поток.

### 2.3. Тяжёлые процессы отдельно от `max_concurrency`
Поле `heavy_jobs` есть. Значение `-1` (по умолчанию) сохраняет прежнюю формулу `max(1, min(2, max_concurrency))`. На профиле hf у formular `heavy_jobs = 1`. Свой семафор formular по-прежнему пропускает одну конвертацию.

### 2.4. Временный диск
`temp_mb` считается по всему runtime-каталогу, включая кэш. После поднятия лимита formular сам держит подбюджеты: `FORMULAR_MODEL_CACHE_MB` (LRU-вытеснение моделей), `FORMULAR_JOB_DISK_MB` (файлы рабочих пространств; при переполнении новые задачи ждут или отклоняются). Так worker не упрётся в лимит супервизора и не будет убит.

## 3. Docker-образ

Корневой `Dockerfile` общий для всех проектов. Каждый пакет увеличивает образ и время сборки (лимиты сборки на HF не опубликованы), поэтому добавлять по этапам.

| Этап | apt-пакеты | Зачем | Лицензия |
|---|---|---|---|
| 0 | проверить, что шрифты с кириллицей уже есть (иначе `fonts-dejavu-core`, `fonts-liberation2`) | вывод LibreOffice и PDF с кириллицей | свободные |
| 5 | `qpdf` | операции с PDF | Apache-2.0 |
| 5 | `graphviz` | DOT → SVG/PNG/PDF | EPL-2.0 (CLI) |
| 5 | `mkvtoolnix` | MKV, дорожки, субтитры | GPL-2.0 (CLI) |
| 5 | `libimage-exiftool-perl` | метаданные | Artistic/GPL (CLI) |
| 6 | `tesseract-ocr`, `tesseract-ocr-rus`, `tesseract-ocr-eng` | OCR | Apache-2.0 |
| 8 | `default-jre-headless` | jadx, CFR, Vineflower | GPL с исключением classpath |
| 8+ | Ghidra (архив с официального релиза при сборке) | нативная декомпиляция | Apache-2.0, около 1 ГБ |

Python-зависимости formular (`formular/requirements.txt`, ставятся в отдельный venv проекта) — по этапам:
- **2:** клиент Mongo уже есть в корневых requirements; `defusedxml`.
- **5:** `pikepdf` (MPL-2.0), `pypdfium2` (Apache/BSD), `pysubs2` (MIT), `duckdb` (MIT), `python-docx` (MIT), `python-pptx` (MIT), `openpyxl` (уже есть), `fonttools` (MIT), `segno` (BSD), `zxing-cpp` (Apache-2.0), `vtracer` (MIT).
- **6:** `huggingface_hub` (Apache-2.0), `onnxruntime` (MIT), `sherpa-onnx` (Apache-2.0), `ctranslate2` (MIT), `faster-whisper` (MIT), `rapidocr-onnxruntime` (Apache-2.0).
- **10:** при необходимости — PyTorch, `diffusers`.

До этапа 10 PyTorch не тянуть: это +1–2 ГБ образа и много памяти.

Браузерные зависимости:
- Новый интерфейс, скорее всего, потребует сборки: модули, Web Workers, Mediabunny, Transformers.js. Оркестратор поддерживает `npm_build = true` и `package.json` (`build.sh` вызывает `npm ci && npm run build`).
- Крупные wasm-файлы: jsDelivr отдаёт не все (на pandoc.wasm был ответ 403). Варианты — собственная раздача из `static/vendor/`, скачанная при сборке (не хранить многомегабайтные бинарники в git), или ленивая загрузка с CDN, который их отдаёт.
- Модели для браузера браузер скачивает напрямую с CDN Hugging Face; сервер их не раздаёт.
- Серверные модели по умолчанию можно скачивать заранее через `preload_from_hub` в метаданных Space (`docs/hf-space/README.md`). Работает ли это для Docker SDK, нужно проверить. Минусы: больше образ, дольше сборка, правка метаданных затрагивает весь Space. По умолчанию модели качаются лениво при первом использовании.

## 4. Cross-origin isolation для многопоточного WASM

Многопоточные ffmpeg.wasm, wasm-vips и некоторые сборки ONNX Runtime требуют `crossOriginIsolated`.
- Заголовки `Cross-Origin-Opener-Policy: same-origin` и `Cross-Origin-Embedder-Policy: require-corp` выставлять **только на HTML formular** (middleware FastAPI), а не через `custom_headers` в README Space: те применяются ко всему Space и могут сломать соседей, которые встраивают сторонние ресурсы.
- Используемые CDN (jsDelivr, cdnjs, Google Fonts) отдают `Cross-Origin-Resource-Policy: cross-origin` и совместимы. Ресурсы без CORP или CORS перестанут грузиться — проверить виджет доната и иконки.
- Изоляция работает при прямом заходе на `*.hf.space`. Внутри iframe на huggingface.co — нет. Без изоляции браузерный исполнитель откатывается на однопоточные варианты.

## 5. Тесты, CI и политика хостинга

При изменении кода formular синхронно обновлять:
- `tests/test_hosting_policy.py::test_html_to_pdf_keeps_an_office_fallback` — ищет строки в `formular/core/converter.py`. Если HTML → PDF переезжает в другой модуль, перенести и проверку, сохранив фоллбэк через LibreOffice.
- `tests/test_hosting_policy.py::test_formular_browser_runtime_is_scrubbed_from_the_space_tree` — ожидает `pymupdf` и `python-magic` в опубликованных requirements. Если PyMuPDF заменяется, обновить ожидание.
- `.github/workflows/sync-to-hf.yml` — `test ! -e formular/core/html_pdf.py`.
- `orchestrator/hosting_policy.py` — `LOCAL_PRINT_MODULE`, `scrub_delete_paths`, `_rewrite_published_text` для `formular/requirements.txt`, `audit_local_print_module`.
- Новые тесты formular класть в `tests/` корня (CI запускает `pytest -q tests`) или в `formular/tests/` с подключением в CI.

## 6. Секреты на HF

Уже есть: `MONGODB_URI`, `CLOUDINARY_*` (используются netlazy и soon, не formular). Новых секретов formular не добавлять: ни `FORMULAR_HF_TOKEN` (решение D14), ни ключей Cloudinary в окружение formular (решение D13).

Добавление секрета — изменение настроек Space с перезапуском, и его влияние на legacy-статус неизвестно. Без отдельного согласия владельца секреты Space не трогать.

### Что нельзя делать с Space
Список и причины — в `02-constraints.md`, раздел 1:
- не ставить на паузу;
- не менять железо даже временно;
- не переименовывать, не переносить и не дублировать;
- не менять SDK;
- не монтировать бакеты как тома;
- не делать factory rebuild без крайней необходимости.

Метаданные Space меняются только через `docs/hf-space/README.md` в обычном деплое; любое изменение метаданных запускает пересборку.

## 7. Порядок внедрения и проверка

Порядок:
1. `max_concurrency` и короткие запросы (опрос вместо долгих соединений).
2. Политика CPU, низкий приоритет и ограничение потоков.
3. Маркер занятости для фоновых задач.
4. Сеть и переменные окружения Mongo. Cloudinary и `FORMULAR_HF_TOKEN` не подключать (D13, D14).
5. Подъём `temp_mb`, `fsize_mb` и `memory_mb` — когда появится AI.

После каждого шага:
- `GET /healthz` и `GET /api/status` — память и состояние всех проектов, нет ли рестартов и открытого circuit breaker;
- длинная конвертация видео (больше 2 минут) — worker не убит, соседние страницы (лендинг, `ascii-city`, `netlazy`) открываются без задержек;
- рестарт Space (push) — задачи восстанавливаются или честно помечаются `interrupted`;
- использование диска formular остаётся в пределах подбюджетов;
- `python -m orchestrator.config --profile hf validate`, `python -m orchestrator.hosting_policy --profile hf`, `pytest -q tests`.
