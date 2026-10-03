# Исследование: проверенные факты и открытые вопросы

Факты проверены 2026-10-03. Отметка «(проверено вручную)» означает прямую проверку API или живого Space, остальное — по указанным источникам. Перед реализацией перепроверять всё, что могло измениться.

## 1. Платформа Hugging Face

- `cpu-basic`: 2 vCPU, 16 ГБ RAM, 50 ГБ непостоянного диска; исходящие соединения документированно разрешены на порты 80, 443 и 8080. Источник: https://huggingface.co/docs/hub/spaces-overview
- Сон: бесплатный Space засыпает через 48 часов после последнего запроса; фоновые задачи активностью не считаются; первый визит будит. Источник: https://huggingface.co/docs/huggingface_hub/package_reference/space_runtime
- Сборка: `startup_duration_timeout` по умолчанию 30 минут (можно `1h`), `preload_from_hub` скачивает модели при сборке. Лимиты времени сборки и размера образа не опубликованы. Источник: https://huggingface.co/docs/hub/spaces-config-reference
- **Платёжная стена с ~8 июля 2026.**
  - Создание, дублирование и перенос Gradio/Docker Spaces на `cpu-basic` требуют PRO, без подписки — HTTP 402.
  - Бесплатным аккаунтам старше 30 дней с подтверждённой почтой разрешено до двух ZeroGPU-Spaces (только Gradio).
  - Внедрялось постепенно, анонса не было.

  Источники:
  - https://huggingface.co/docs/hub/spaces-overview
  - https://github.com/huggingface/hub-docs/pull/2624
  - https://discuss.huggingface.co/t/docker-sdk-now-marked-as-paid-when-creating-a-new-space/177580
  - https://discuss.huggingface.co/t/official-community-complaint-revert-free-cpu-basic-spaces-and-remove-anti-developer-sdk-restrictions/177703
- **Риски для legacy-Spaces.**
  - Space на `cpu-basic`, стоявший на ручной паузе, не удалось запустить снова; сотрудник HF ответил: «To unlock cpu-basic hardware for your Space, upgrade to PRO» (27.08.2026): https://discuss.huggingface.co/t/403-cpu-basic-quota-limit-on-my-only-space-maelanoi-plantdoctor-ai/179309
  - Вернуться на `cpu-basic` с другого железа — только с PRO.
  - По замеру пользователя на 05.09.2026, из 250 Spaces, созданных до июня, работают 249.
- **Space `Nargan/projects`** (проверено вручную, `https://huggingface.co/api/spaces/Nargan/projects`):
  - создан 2026-05-11, последнее изменение 2026-09-30T15:02:20Z — совпадает с коммитом `7f3f2d6` от 22:02 (UTC+7);
  - `runtime.stage = RUNNING`, `runtime.sha` равен `sha`, железо `cpu-basic`;
  - пересборки legacy-Space работают; владелец подтвердил legacy-статус.
- Живой Space (проверено вручную): `/healthz` → `{"status":"ok","profile":"hf","isolation":"isolated","database":"online"}`; все проекты в `/api/status` — `stopped` (ленивый запуск).
- **ZeroGPU:**
  - железо — RTX Pro 6000 Blackwell;
  - суточные квоты: аноним — 2 минуты, бесплатный аккаунт — 5, PRO — 40, Enterprise — 60;
  - при вызове с сервера квота списывается с forwarded `X-IP-Token`, затем с владельца токена, затем с IP;
  - при прямом заходе на `*.hf.space` данные входа для квоты не передаются.

  Источники: https://huggingface.co/docs/hub/spaces-zerogpu, https://gradio.app/docs/python-client/using-zero-gpu-spaces
- **Исключено решением D2, но существует:**
  - вход через HF работает и в Docker Spaces (`hf_oauth: true`, scope `inference-api`, токен до 30 дней): https://huggingface.co/docs/hub/spaces-oauth
  - Inference Providers: $0,10 в месяц бесплатным аккаунтам, $2 для PRO: https://huggingface.co/docs/inference-providers/pricing
- **Content Policy:** https://huggingface.co/content-policy
  - Сексуальный контент без согласия и любой с несовершеннолетними запрещён; остальной NSFW допустим с тегом.
  - Сотрудник HF в 2023 году советовал не использовать Spaces как бэкенд внешних приложений («Spaces are designed for demos»): https://discuss.huggingface.co/t/using-a-space-as-a-backend/37258
- **Ложные срабатывания автосканера:**
  - детектор `RepoScanner` (категория туннелей) сработал на упоминание CDN-провайдера в файле документации к API; флаг остался и после удаления файла: https://discuss.huggingface.co/t/space-flagged-as-abusive-false-positive-cannot-restart-after-removing-flagged-file/173676 и https://discuss.huggingface.co/t/space-wrongly-flagged-as-abusive/178494
  - отдельный случай с вердиктом про прокси на порту 7860 (апрель 2026).

  Снять флаг может только поддержка HF.
- **Storage Buckets:**
  - квота бесплатного аккаунта — 100 ГБ приватного хранения, общая с репозиториями, докупить нельзя; трафик и CDN включены;
  - S3 API на `https://s3.hf.co/<namespace>`, правил автоудаления нет;
  - с 31.03.2026 бакет можно смонтировать в Space как том;
  - подписанные GET-ссылки подтверждены только сторонним тестом.

  Источники:
  - https://huggingface.co/docs/hub/storage-limits
  - https://huggingface.co/docs/hub/storage-buckets-s3
  - https://huggingface.co/changelog/storage-buckets-for-spaces
  - https://huggingface.co/docs/hub/spaces-storage

  Старый persistent storage свёрнут.
- **Лимиты Hub API** за 5 минут (API / скачивание / страницы): аноним — 500 / 3000 / 100 на IP, бесплатный аккаунт — 1000 / 5000 / 200, PRO — 2500 / 12000 / 400. При превышении — 429 с заголовками RateLimit. Источник: https://huggingface.co/docs/hub/rate-limits

## 2. Внешние сервисы

- **Cloudinary Free:**
  - 25 кредитов за скользящие 30 дней (1 кредит = 1 ГБ хранения, или 1 ГБ трафика, или 1000 трансформаций);
  - raw и изображения — до 10 МБ, видео — до 100 МБ; Admin API — 500 запросов в час, Upload API без лимита частоты;
  - выдача PDF и ZIP по умолчанию заблокирована;
  - `private_download_url` не кэшируется и считается как двойной трафик;
  - нативного автоудаления нет.

  Источники:
  - https://cloudinary.com/documentation/pricing.md
  - https://cloudinary.com/documentation/image_delivery_options
  - https://cloudinary.com/documentation/control_access_to_media
- **Условия Cloudinary** разрешают любые типы файлов. AUP:
  - п. 4.1 — запрет нескольких аккаунтов ради обхода лимитов;
  - п. 4.3 — запрет «чрезмерного использования»;
  - п. 5 — право сканировать контент;
  - п. 6.4 — блокировка аффилированных аккаунтов.

  Публичных случаев блокировки именно за зашифрованные raw-файлы не найдено. Источники: https://cloudinary.com/tou, https://cloudinary.com/trust/aup
- **MongoDB Atlas Free (M0):**
  - 512 МБ, 100 операций в секунду, 500 соединений;
  - 10 ГБ входящего и исходящего трафика за 7 дней;
  - до 5 change streams, TTL-индексы, 500 коллекций, бэкапов нет;
  - Flex — $8–30 в месяц.

  Источник: https://www.mongodb.com/docs/atlas/reference/free-shared-limitations
- **Очереди:**
  - `mongo-taskqueue` 1.0.4 — аренды, heartbeat, повторы, дедупликация, приоритеты: https://pypi.org/project/mongo-taskqueue/
  - в Celery 5.6 брокера MongoDB нет;
  - бесплатный Upstash Redis — 500 тысяч команд в месяц.
- **Отклонённые хранилища:**
  - хранилище CDN-провайдера из правила `tunnel_worker` — нужна карта, риск сканера;
  - Backblaze B2, 10 ГБ бесплатно — правила удаления только в днях;
  - Supabase, 1 ГБ, файл до 50 МБ — засыпает после недели простоя;
  - Google Drive — у сервисного аккаунта нет квоты;
  - Telegram — условия запрещают облачные хранилища;
  - Dataset-репозитории HF — удалённые файлы занимают квоту.

## 3. API Hugging Face для автоподбора моделей (проверено вручную)

- `GET /api/models?pipeline_tag=automatic-speech-recognition&sort=trendingScore&expand[]=safetensors&expand[]=cardData&expand[]=gated&...` отдаёт `library_name`, `safetensors.total`, `gated`, `downloads`, `trendingScore`, `cardData.license`, `cardData.language`.
- Первые результаты trending для ASR — модель под MLX, модель на transformers и пайплайн диаризации: одна популярность шумит.
- `GET /api/datasets?filter=benchmark:official` — 48 датасетов, в том числе `hf-audio/open-asr-leaderboard`, `allenai/olmOCR-bench`, `PaddlePaddle/Real5-OmniDocBench`, `llamaindex/ParseBench`, `mteb/*`, `MMMU/MMMU_Pro`, `MME-Benchmarks/Video-MME-v2`.
- `GET /api/datasets/hf-audio/open-asr-leaderboard/leaderboard` — массив `{rank, modelId, value, verified, filename: ".eval_results/...", ...}`. Верх таблицы (WER):
  - Edge0/ARK-ASR-3B — 4,76;
  - MOSS-Transcribe-preview-2B — 4,87;
  - Cohere transcribe 03-2026 — 5,42;
  - Qwen3-ASR-1.7B — 5,76;
  - nvidia/parakeet-tdt-0.6b-v2 — 6,05.
- `GET /api/datasets/allenai/olmOCR-bench/leaderboard` — верх таблицы: Infinity-Parser2-Pro (87,6), chandra-ocr-2 (85,8), dots.mocr (83,9).
- **Смысл `verified` в `.eval_results`:**
  - «verified» — оценка прошла в HF Jobs через inspect-ai с валидным токеном проверки;
  - «community» — результат из открытого PR;
  - остальное — самоотчёт автора модели.

  Функция помечена как «work in progress». Источники: https://huggingface.co/docs/hub/eval-results, https://huggingface.co/docs/hub/leaderboard-data-guide

## 4. Производительность и модели

- **llama.cpp на 2 vCPU:** Llama 3.2 1B Q4_K_M — 6,1 токена в секунду (https://www.tencentcloud.com/techpedia/147077). На Raspberry Pi 5: 1B — 9–10, 3B — около 4, 8B — 1,6 токена в секунду.
- **Распознавание речи:**
  - Parakeet-TDT-0.6B-v3 int8 ONNX — RTF 0,031 на 4 ядрах (https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3);
  - GigaAM-v3 — MIT, лучший для русского (https://github.com/salute-developers/GigaAM);
  - faster-whisper small int8 — примерно в 7,6 раза быстрее реального времени на 8 потоках.
- **Piper:** движок под GPL-3.0 с версии 1.3.0 (https://github.com/OHF-Voice/piper1-gpl); RTF около 0,35 в контейнере на 2 ядра.
- **Silero:** русские модели v5 — CC-BY-NC, `v5_cis_base` — MIT (https://github.com/snakers4/silero-models).
- **FastSD CPU:** SD-Turbo — 7,8 с за картинку 512 px на i7-12700 в PyTorch; режим OpenVINO требует 9–11 ГБ RAM (https://github.com/rupeshs/fastsdcpu).
- **Wan 2.1 1.3B:** 4–5 минут на 5 секунд видео 480p даже на RTX 4090 (https://blog.salad.com/benchmarking-wan2-1/).
- **TripoSR (MIT):** на CPU около 6 минут в одном отчёте (https://github.com/VAST-AI-Research/TripoSR).
- **Hunyuan3D** не действует в ЕС, Великобритании и Южной Корее (https://huggingface.co/tencent/Hunyuan3D-2.1/blob/main/LICENSE).
- **BabelDOC и pdf2zh-next** — AGPL-3.0; модель вёрстки в ONNX работает локально на CPU; есть офлайн-ассеты (https://pypi.org/project/BabelDOC/).
- **argos-translate-files:** форматы txt, odt, odp, docx, pptx, epub, html, srt, pdf; репозиторий LibreTranslate под AGPL-3.0, старый форк под MIT без srt и pdf (https://github.com/LibreTranslate/argos-translate-files).
- **Ghidra:** JDK 21, минимум 4 ГБ RAM (рекомендуется 8), около 1 ГБ на диске; у `analyzeHeadless` есть `-max-cpu` и `-analysisTimeoutPerFile` (https://www.ghidradocs.com/11.4.3_PUBLIC/support/analyzeHeadlessREADME.html).

## 5. Браузер

- **Mediabunny** (MPL-2.0) поверх WebCodecs: смена контейнера, транскод, обрезка, замена дорожек, потоковая запись (https://mediabunny.dev/guide/converting-media-files).
- **ffmpeg.wasm** в 12–25 раз медленнее нативного FFmpeg, потолок около 2 ГБ, ядро под GPL (https://ffmpegwasm.netlify.app/docs/performance/).
- **WebCodecs:** Chrome/Edge 94+, Firefox 130+ (кроме Android), Safari 26+ (https://caniuse.com/webcodecs).
- **WebGPU:** Chrome/Edge, Safari 26, Firefox на Windows и macOS (https://github.com/gpuweb/gpuweb/wiki/Implementation-Status).
- **Transformers.js v4** (https://huggingface.co/blog/transformersjs-v4); **pandoc.wasm** — с pandoc 3.9 (https://github.com/jgm/pandoc/releases/tag/3.9), jsDelivr на него отвечал 403.
- Работа после закрытия вкладки невозможна; `custom_headers` в README Space применяются ко всему Space.

## 6. Безопасность ссылок, право, протоколы

- **Неугадываемые ссылки** (W3C TAG): только HTTPS, ограниченный срок, никаких сторонних скриптов на странице, `Referrer-Policy: no-referrer`, запрет в robots, лимит на перебор, 404/410 после истечения, в базе — только хэш токена (https://w3ctag.github.io/capability-urls/).
- **EU AI Act, статья 50**, применяется со 2 августа 2026 года.
  - Digital Omnibus (Регламент (ЕС) 2026/1744 от 8 июля 2026, в силе с 27 июля) отсрочил до 2 декабря 2026 года только машиночитаемую маркировку и только для систем, выпущенных до 2 августа 2026 года.
  - Он же с 2 декабря 2026 года запрещает системы, генерирующие интимные изображения реальных людей без согласия и CSAM.
  - Провайдером считается и бесплатный сервис; исключение для open-source на статью 50 не распространяется.

  Источники:
  - https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act
  - https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32026R1744
- **DSA, статья 16:** хостинг, включая файлообменники, обязан иметь механизм приёма жалоб на незаконный контент (https://eur-lex.europa.eu/eli/reg/2022/2065/oj/eng). В США: DMCA-агент даёт safe harbor, о CSAM нужно сообщать в NCMEC при фактическом знании.
- **Существующие решения:**
  - CloudConvert — граф задач, ссылки на 24 часа, webhook с HMAC (https://cloudconvert.com/api/v2/jobs);
  - Transloadit — роли входов `use: [{name, as}]` (https://transloadit.com/docs/topics/assembly-instructions/);
  - Stirling-PDF — пайплайны в JSON, без разнотипных входов в UI (https://docs.stirlingpdf.com/Configuration/Automation/Pipeline/);
  - ConvertX — 21 движок, без цепочек (https://github.com/C4illin/ConvertX);
  - VERT — WASM в браузере, видео на сервере (https://github.com/VERT-sh/VERT).
- **MCP:** спецификация 2026-07-28 и расширение Tasks (https://modelcontextprotocol.io/extensions/tasks/overview); MCP-серверы есть у CloudConvert (https://cloudconvert.com/blog/mcp-server) и Transloadit (https://transloadit.com/docs/sdks/mcp-server/).

## 7. Открытые вопросы — проверить до реализации

1. Убивает ли супервизор длинное кодирование видео на Space сейчас (`01-current-state.md`, P6).
2. Сколько памяти реально занимают соседние проекты под нагрузкой (`/api/status`) — чтобы выбрать `memory_mb` для formular.
3. Есть ли в образе шрифты с кириллицей для LibreOffice → PDF.
4. HF Buckets: подписанные PUT и CORS для загрузки из браузера; лимиты трафика на бесплатном аккаунте. Монтирование в legacy-Space не рассматривается.
5. Таймауты обратного прокси HF для долгих запросов и лимит размера тела запроса (не документированы).
6. Проходят ли заголовки COOP/COEP со страниц formular через прокси HF на `*.hf.space`.
7. Работает ли `preload_from_hub` для Docker SDK.
8. Скорость моделей-кандидатов на cpu-basic (распознавание речи, OCR, LLM, TripoSR); есть ли у процессоров HF AVX-512 и AMX.
9. Лицензии конкретных кандидатов: Kandinsky 2.2, Würstchen v2, Swin2SR, модели вёрстки Docling, модели диаризации sherpa-onnx, пакеты Argos, модели Bergamot, модель RNNoise для `arnndn`, чекпойнты LLM4Decompile, русские голоса Piper, unluac, odfpy, ffsubsync, SoundFont для FluidSynth, c2pa-python.
10. Как HF поступит с legacy-Space после factory rebuild, смены секретов или долгого сна. До выяснения таких действий не делать (`02-constraints.md`, раздел 1).

## 8. Неопределённости

- Цифры производительности для 2 vCPU в основном экстраполированы с более мощных процессоров.
- Поведение автосканера HF непредсказуемо: соблюдение списка триггеров снижает риск, но не исключает его.
- Политика HF в отношении legacy-Spaces может измениться без объявления, как это было в июле 2026 года.
