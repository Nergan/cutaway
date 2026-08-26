# Деплой `another` внутри монорепозитория `cutaway`

Здесь только про то, как `another` живёт внутри `cutaway` и как его развернуть.
Архитектура самого проекта — в `docs/architecture.md`, устройство авторизации —
в `docs/auth-spec.md`.

Уже развернули и хотите пустить через систему свой трафик — вам нужен
[GETTING-STARTED.md](GETTING-STARTED.md): там пошагово от приглашения в админке
до работающего туннеля, и там же честно перечислено, что пока не работает.

Все команды в этом документе даны **для PowerShell на Windows**, потому что
именно там ведётся разработка. Где для Linux/macOS нужна другая запись, это
отмечено отдельно.

## Из чего состоит система

У `another` две независимые половины, и их деплоят по-разному:

1. **Origin (control plane)** — Python-приложение. Едет на Hugging Face Space
   вместе со всем остальным монорепозиторием, как обычный плагин `cutaway`.
2. **Edge (воркер)** — TypeScript на Cloudflare Workers. Деплоится отдельно,
   прямо из GitHub Actions в Cloudflare.

Один `git push` в `main` запускает оба пути:

```
git push (main)
   │
   ├─► .github/workflows/sync-to-hf.yml
   │      зеркалит весь репозиторий в HF Space Nargan/projects
   │      → docker build (корневой Dockerfile → build.sh → start.sh)
   │      → uvicorn main:app на порту 7860
   │      → плагин another доступен под префиксом /another
   │
   └─► .github/workflows/another-edge-deploy.yml
          срабатывает только если менялось что-то в another/edge/**
          → npx wrangler deploy → Cloudflare Worker «another-edge»
```

Связаны эти половины двумя URL и одним общим секретом:

| Кто кого зовёт | По какому адресу | Чем подтверждает, что он свой |
| --- | --- | --- |
| воркер → origin | `MONGO_REST_PROXY_URL` + `/internal/v1/...` | заголовок `X-Another-Proxy-Secret` |
| origin → воркер | `EDGE_INTERNAL_URL` + `/internal/ban-invalidate` | тот же заголовок |

Значение секрета одно и то же с обеих сторон. На HF оно называется
`ANOTHER_SERVICE_SECRET`, в Cloudflare — тоже `ANOTHER_SERVICE_SECRET`.
Если они разойдутся, воркер начнёт получать от origin `401`.

## Какие адреса появляются в Space

Плагин `another/main.py` монтирует FastAPI-приложение из
`control-plane-admin/another_admin` как под-приложение по префиксу `/another`:

| Адрес | Что там |
| --- | --- |
| `https://nargan-projects.hf.space/another/` | редирект на админку |
| `https://nargan-projects.hf.space/another/admin/` | веб-админка (ключ живёт только в памяти вкладки) |
| `https://nargan-projects.hf.space/another/admin/v1/*` | admin API, гибридные подписи Ed25519 + ML-DSA-65 |
| `https://nargan-projects.hf.space/another/internal/v1/*` | REST-прокси к Mongo, только для воркера |
| `https://nargan-projects.hf.space/another/health` | проверка живости |

Карточки на главной странице `cutaway` у `another` нет намеренно: проект не
публичный, адрес надо знать.

Пока не заданы `MONGO_URI` и `ANOTHER_SERVICE_SECRET`, API отвечает `503` с
текстом причины (а не `500`) и не роняет остальные плагины хаба. При этом
админка и `/health` всё равно открываются — по ним и видно, чего не хватает.

---

## Шаг 1. Секреты в HF Space

Открыть Space `Nargan/projects` → Settings → Variables and secrets. Добавлять
именно как **secrets**, не как variables:

| Ключ | Что положить | Как получить |
| --- | --- | --- |
| `ANOTHER_SERVICE_SECRET` | случайная строка на 32+ байта | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `EDGE_INTERNAL_URL` | `https://another-edge.<субдомен>.workers.dev` | появится после шага 3 |
| `ANOTHER_CONTROL_PLANE_URL` | тот же адрес воркера | то же |

`MONGO_URI` задавать **не нужно**. Плагин переиспользует уже существующий
секрет `MONGODB_URI` того же кластера, а имя базы по умолчанию — `another`.
Создавать базу `another` руками тоже не нужно: `ensure_schema()` сам создаст
и её, и все индексы при первом обращении.

## Шаг 2. Секреты в GitHub

Репозиторий → Settings → Secrets and variables → Actions:

| Ключ | Где взять |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | dash.cloudflare.com → My Profile → API Tokens → Create Token → шаблон **Edit Cloudflare Workers** |
| `CLOUDFLARE_ACCOUNT_ID` | dash.cloudflare.com → Workers & Pages → Account ID в правой колонке |

Токену нужны права `Account → Workers Scripts → Edit`,
`Account → Workers KV Storage → Edit` и `Account → Account Settings → Read`.
Шаблон «Edit Cloudflare Workers» выдаёт ровно их, вручную ничего добавлять не
надо.

Workflow деплоит из GitHub Environment с именем `production`. Секреты можно
положить либо на этот environment (тогда доступны required reviewers и прочие
protection rules), либо просто на репозиторий — джоб увидит и те, и другие.

## Шаг 3. Первый деплой воркера — один раз руками

CI не может сделать этот шаг сам по двум причинам: нужно создать KV namespace
(его id потом коммитится в `wrangler.toml` литералом) и положить секрет в
Cloudflare. Дальше CI будет деплоить сам.

```powershell
cd another\edge
npm ci

# 1. Вход в Cloudflare через браузер.
#    Альтернатива без браузера: $env:CLOUDFLARE_API_TOKEN = "<токен>"
npx wrangler login

# 2. Создать KV namespace под бан-кэш и хранилище сессий
npx wrangler kv namespace create BAN_CACHE
```

Последняя команда напечатает примерно это:

```
[[kv_namespaces]]
binding = "BAN_CACHE"
id = "6e88f186512c4f23bc75aa7b5a415b1a"
```

Этот `id` надо вписать в `another/edge/wrangler.toml` вместо
`CHANGE_ME_kv_namespace_id` и закоммитить. Сам id секретом не является: без
токена доступа к аккаунту он бесполезен, и Cloudflare сама предполагает, что
он лежит в репозитории.

```powershell
# 3. Секрет, которым воркер подписывает запросы к origin.
#    Ввести ровно то же значение, что в ANOTHER_SERVICE_SECRET на HF.
npx wrangler secret put ANOTHER_SERVICE_SECRET

# 4. Проверка сборки и биндингов без публикации.
#    --outdir указываем вне репозитория, чтобы бандл не мусорил в git.
npx wrangler deploy --dry-run --outdir $env:TEMP\another-dryrun

# 5. Первый настоящий деплой
npx wrangler deploy
```

Wrangler напечатает адрес воркера — `https://another-edge.<субдомен>.workers.dev`.
Его и надо положить в `EDGE_INTERNAL_URL` и `ANOTHER_CONTROL_PLANE_URL` на HF
(шаг 1).

### Две вещи, на которых легко застрять

**Версия wrangler.** В `package.json` изначально стоял `wrangler ^3.78.0`, а с
третьей версией современный Cloudflare уже ругается. Нужна 4.x:

```powershell
npm install --save-dev wrangler@^4
```

**Durable Objects на бесплатном плане.** В блоке `[[migrations]]` в
`wrangler.toml` должно быть `new_sqlite_classes`, а не `new_classes`. Бесплатный
план разрешает только Durable Objects с SQLite-хранилищем, и на `new_classes`
деплой падает с ошибкой про биллинг.

## Шаг 4. Проверить, что половины видят друг друга

```powershell
# origin поднялся и Mongo доступна
curl.exe https://nargan-projects.hf.space/another/health

# воркер жив
curl.exe https://another-edge.<субдомен>.workers.dev/health
```

Дальше проверяем, что внутренний API закрыт от посторонних. В PowerShell важно
писать `curl.exe`, а не `curl`: без `.exe` это алиас на `Invoke-WebRequest`,
который не понимает флаги настоящего curl. И одинарные кавычки внутри JSON
PowerShell съедает, поэтому кавычки надо экранировать обратным слэшем.

```powershell
# Ожидаем 401 — секрета нет, значит и разговаривать не о чем.
curl.exe -s -o NUL -w "%{http_code}`n" -X POST `
  https://nargan-projects.hf.space/another/internal/v1/clients/find `
  -H "Content-Type: application/json" -d '{\"client_id\":\"x\"}'

# Ожидаем 404 — секрет верный, просто такого клиента нет.
curl.exe -s -o NUL -w "%{http_code}`n" -X POST `
  https://nargan-projects.hf.space/another/internal/v1/clients/find `
  -H "Content-Type: application/json" `
  -H "X-Another-Proxy-Secret: $env:ANOTHER_SERVICE_SECRET" `
  -d '{\"client_id\":\"x\"}'
```

Если во второй команде вернулось `401` — значение секрета на HF и в Cloudflare
разошлось. Если `422` — до сервера доехало битое тело запроса, то есть кавычки
всё-таки съелись; проще тогда проверить через `Invoke-RestMethod`:

```powershell
$body = @{ client_id = "x" } | ConvertTo-Json
Invoke-RestMethod -Method Post -SkipHttpErrorCheck `
  -Uri https://nargan-projects.hf.space/another/internal/v1/clients/find `
  -ContentType "application/json" -Body $body
```

На Linux/macOS те же две проверки выглядят обычным образом:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://nargan-projects.hf.space/another/internal/v1/clients/find \
  -H 'Content-Type: application/json' -d '{"client_id":"x"}'
```

## Шаг 5. Завести первого админа

Веб-админка не умеет регистрировать сама себя: первая запись админа кладётся в
Mongo в обход неё — с локальной машины через CLI.

```powershell
cd another\control-plane-admin
pip install -e .

$env:MONGO_URI = "<та же строка, что MONGODB_URI в Space>"
$env:MONGO_DB_NAME = "another"

another-admin keygen --admin-id me --output $HOME\me.another-admin-key
another-admin admin-register --keyfile $HOME\me.another-admin-key
```

После этого открыть `/another/admin/`, выбрать файл ключа, ввести passphrase и
нажать «Unlock + bootstrap». Ключ никогда не покидает вкладку: подписи
считаются прямо в браузере (WebCrypto + `@noble/post-quantum`).

Файл ключа — единственный способ попасть в админку. Потеряется — придётся
заводить нового админа тем же CLI.

### Если после Unlock ничего не происходит

Первым делом открыть консоль браузера (F12 → Console). Вся логика панели живёт
в одном ES-модуле, и если он не загрузился, то не сработает ничего — молча, без
сообщения в интерфейсе. Само сообщение будет в консоли.

Внешних зависимостей у панели нет: криптография (`vendor/noble-crypto.js`) и
шрифты (`vendor/fonts/`) лежат в репозитории и отдаются тем же Space. Так что
недоступность CDN или блокировщик сторонних скриптов эту панель сломать не
могут — раньше могли, теперь нет.

Что реально встречается:

- **`Failed to load module script: ... MIME type of "text/plain"`** — только при
  локальном запуске под Windows. `StaticFiles` берёт Content-Type из
  `mimetypes`, а тот читает типы из реестра Windows, где `.js` нередко объявлен
  как `text/plain`; браузер отказывается исполнять такой ответ как модуль.
  В коде это уже обойдено через `mimetypes.add_type` в
  `another_admin/api/app.py`, но если правили этот файл — проверьте, что вызов
  на месте. В Docker-образе на Hugging Face проблемы нет: там Linux.
- **`401` в ответах админ-API** — passphrase не тот, либо ключ этого админа не
  зарегистрирован в базе (`admin-register` не выполнялся или выполнялся против
  другой базы).
- **Пустые панели без ошибок** — это норма на свежей установке: устройств,
  сессий и событий ещё нет.

---

## Что осталось за рамками этого деплоя

- **Data plane на HF не работает.** Узел `hf-space` в `NODES_JSON`
  (`wrangler.toml`) предполагает VLESS-over-WS на origin, а это Go-сайдкары
  (`core/cmd/xhttp-origin`, `reality-origin`). В образе `cutaway` их нет: ни
  Go-тулчейна, ни второго порта — Space отдаёт только 7860. На HF живёт
  исключительно control plane, а Tier1-трафик идёт через сам воркер (`/proxy`).
  Понадобится origin data-plane — это отдельный деплой из
  `deploy/origin/Dockerfile` на Render или VPS.
- **`op build_installer` в админке отвечает, но не компилирует.**
  `ANOTHER_BUILD_ENABLED` выключен, а `core/` исключён из образа через
  `.dockerignore`. Кнопка «Собрать» вернёт план сборки с командами —
  компилировать надо локально.
- **Telegram-бот в дереве есть, но из монолита не запускается.** `aiogram` и
  `typer` не входят в `another/requirements.txt`. Workflow
  `admin-bot-deploy.yml` в монорепозиторий не переносился: он пушил образ бота
  в GHCR на каждое изменение `control-plane-admin/**`, что здесь только шум.
  Понадобится — восстановить из истории `another`.

## Свой домен в Cloudflare (когда появится)

`infra/cloudflare/` создаёт CNAME на воркер и гасит ECH (без этого ТСПУ видит
ECH-пакеты). Требует своей зоны, поэтому в CI не включён. И до включения надо
починить две вещи:

1. **Хранение state.** Сейчас Terraform держит state локально, то есть каждый
   прогон CI начинал бы с пустого state и заводил новый KV namespace. Нужен
   remote backend (R2/S3) — либо вообще убрать KV из Terraform и оставить его
   за `wrangler`. Второе проще и фактически уже сделано.
2. **Версия провайдера.** `main.tf` писался под `cloudflare/cloudflare ~> 4.41`
   и ни разу не прогонялся через `terraform validate`. Между 4.x и 5.x у
   провайдера были ломающие изменения, имена атрибутов надо перепроверить.

## Локальная разработка

Весь монолит целиком, как на HF, включая остальные плагины:

```powershell
cd cutaway
pip install -r requirements.txt -r another\requirements.txt
uvicorn main:app --reload --port 7860
# → http://127.0.0.1:7860/another/admin/
```

Только `another`, отдельно (как `Dockerfile.api`). Админка окажется на
`/admin/`, потому что префикса `/another` в этом режиме нет; и то, и другое
работает без правок в коде:

```powershell
cd another\control-plane-admin
python -m another_admin.api   # порт 8080
```

Воркер локально:

```powershell
cd another\edge
Copy-Item ..\.env.example .dev.vars   # оставить только ANOTHER_SERVICE_SECRET
npx wrangler dev
```
