# Деплой `another` в составе монорепозитория `cutaway`

Этот документ описывает только то, что относится к жизни `another` внутри
`cutaway`. Архитектура самого проекта — в `docs/architecture.md`, спека
авторизации — в `docs/auth-spec.md`.

## Как это собрано

```
git push (main)
   │
   ├─► .github/workflows/sync-to-hf.yml
   │      force-push всего репозитория в HF Space Nargan/projects
   │      → docker build (корневой Dockerfile → build.sh → start.sh)
   │      → uvicorn main:app на :7860
   │      → плагин another смонтирован под /another
   │
   └─► .github/workflows/another-edge-deploy.yml  (только при изменениях в another/edge/**)
          npx wrangler deploy → Cloudflare Worker another-edge
```

Origin API и Worker — два независимых деплоя, связанных двумя URL и одним
общим секретом:

| Направление | Куда | Аутентификация |
| --- | --- | --- |
| Worker → origin | `MONGO_REST_PROXY_URL` + `/internal/v1/...` | заголовок `X-Another-Proxy-Secret` |
| origin → Worker | `EDGE_INTERNAL_URL` + `/internal/ban-invalidate` | тот же заголовок |

Значение секрета — одно и то же по обе стороны: `ANOTHER_SERVICE_SECRET`.

## Что даёт монорепозиторий

Плагин `another/main.py` монтирует FastAPI-приложение из
`control-plane-admin/another_admin` как sub-app под `/another`:

| URL в Space | Что это |
| --- | --- |
| `https://nargan-projects.hf.space/another/` | редирект на админку |
| `https://nargan-projects.hf.space/another/admin/` | веб-админка (ключ только в RAM вкладки) |
| `https://nargan-projects.hf.space/another/admin/v1/*` | admin API (гибридные подписи Ed25519 + ML-DSA-65) |
| `https://nargan-projects.hf.space/another/internal/v1/*` | REST-прокси к Mongo для Worker |
| `https://nargan-projects.hf.space/another/health` | healthcheck |

Карточки на главной у `another` нет сознательно — проект не публичный, ссылку
надо знать.

Пока `MONGO_URI`/`ANOTHER_SERVICE_SECRET` не заданы, API отдаёт `503` с текстом
причины, а не `500`, и не роняет остальные плагины хаба. Админка и `/health`
при этом открываются — по ним и видно, что именно не настроено.

---

## Шаг 1. Секреты HF Space

Settings → Variables and secrets в Space `Nargan/projects`. Как **secrets**,
не variables:

| Ключ | Значение | Где взять |
| --- | --- | --- |
| `ANOTHER_SERVICE_SECRET` | случайные 32+ байта | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `EDGE_INTERNAL_URL` | `https://another-edge.<твой-субдомен>.workers.dev` | появится после шага 3 |
| `ANOTHER_CONTROL_PLANE_URL` | тот же URL воркера | то же |

`MONGO_URI` задавать **не нужно**: плагин переиспользует уже существующий
секрет `MONGODB_URI` того же кластера, а `MONGO_DB_NAME` по умолчанию `another`.
Базу `another` создавать вручную тоже не нужно — `ensure_schema()` создаёт её и
все индексы при первом обращении.

## Шаг 2. Секреты GitHub

Settings → Secrets and variables → Actions в `Nergan/cutaway`:

| Ключ | Где взять |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | dash.cloudflare.com → My Profile → API Tokens → Create Token → шаблон **Edit Cloudflare Workers** |
| `CLOUDFLARE_ACCOUNT_ID` | dash.cloudflare.com → Workers & Pages → в правой колонке **Account ID** |

Токену нужны права: `Account → Workers Scripts → Edit`,
`Account → Workers KV Storage → Edit`, `Account → Account Settings → Read`.
Шаблон «Edit Cloudflare Workers» их и выдаёт.

Если позже появится свой домен в Cloudflare — добавятся `CLOUDFLARE_ZONE_ID` и
`CLOUDFLARE_ACCOUNT_SUBDOMAIN` для `infra/cloudflare/` (см. «Свой домен» ниже).

## Шаг 3. Первый деплой воркера — вручную, с локальной машины

Один раз это надо сделать руками: CI не может создать KV namespace и положить
секрет, потому что `wrangler.toml` ссылается на id namespace литералом.

```bash
cd another/edge
npm ci

# 1. Логин в браузере (или экспортируй CLOUDFLARE_API_TOKEN, тогда логин не нужен)
npx wrangler login

# 2. KV namespace для бан-кэша и session store
npx wrangler kv namespace create BAN_CACHE
```

Команда напечатает что-то вида:

```
[[kv_namespaces]]
binding = "BAN_CACHE"
id = "a1b2c3d4e5f6..."
```

Подставь этот `id` в `another/edge/wrangler.toml` вместо
`CHANGE_ME_kv_namespace_id` и закоммить — дальше CI будет деплоить сам.

```bash
# 3. Секрет, которым воркер подписывает запросы к origin.
#    Ввести ровно то же значение, что в ANOTHER_SERVICE_SECRET на HF.
npx wrangler secret put ANOTHER_SERVICE_SECRET

# 4. Проверка сборки и биндингов без публикации
npx wrangler deploy --dry-run --outdir /tmp/dryrun

# 5. Первый реальный деплой
npx wrangler deploy
```

Wrangler напечатает URL воркера — `https://another-edge.<субдомен>.workers.dev`.
Его и надо положить в `EDGE_INTERNAL_URL` и `ANOTHER_CONTROL_PLANE_URL` на HF
(шаг 1).

## Шаг 4. Проверка связки

```bash
# origin поднялся и Mongo доступна
curl https://nargan-projects.hf.space/another/health

# воркер жив
curl https://another-edge.<субдомен>.workers.dev/health

# внутренний API закрыт для чужих
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://nargan-projects.hf.space/another/internal/v1/clients/find \
  -H 'Content-Type: application/json' -d '{"client_id":"x"}'
# ожидаем 401

# и открыт для владельца секрета (404 = секрет верный, клиента просто нет)
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://nargan-projects.hf.space/another/internal/v1/clients/find \
  -H 'Content-Type: application/json' \
  -H "X-Another-Proxy-Secret: $ANOTHER_SERVICE_SECRET" \
  -d '{"client_id":"x"}'
```

## Шаг 5. Первый админ

Веб-админка не умеет регистрировать сама себя: запись админа в Mongo кладётся
аварийным каналом — CLI с локальной машины.

```bash
cd another/control-plane-admin
pip install -e .

export MONGO_URI='<та же строка, что MONGODB_URI в Space>'
export MONGO_DB_NAME=another

another-admin keygen --admin-id me --output ~/me.another-admin-key
another-admin admin-register --keyfile ~/me.another-admin-key
```

Дальше — `/another/admin/`, кнопка «Unlock + bootstrap», файл ключа и
passphrase. Ключ никогда не покидает вкладку: подписи считаются в браузере
(WebCrypto + `@noble/post-quantum`).

Файл ключа — единственный доступ к админке. Потеряешь — заводить нового админа
тем же CLI.

---

## Что осталось за рамками этого деплоя

- **Data plane на HF.** Узел `hf-space` в `NODES_JSON` (`wrangler.toml`)
  предполагает VLESS-over-WS на origin, а это Go-сайдкары
  (`core/cmd/xhttp-origin`, `reality-origin`). В образе `cutaway` их нет:
  ни Go-тулчейна, ни второго порта. На HF работает только control plane;
  Tier1-трафик идёт через сам воркер (`/proxy`). Если понадобится origin
  data-plane — это отдельный деплой из `deploy/origin/Dockerfile` на
  Render/VPS.
- **`op build_installer`** в админке отвечает, но не компилирует:
  `ANOTHER_BUILD_ENABLED` выключен, а `core/` исключён из образа
  (`.dockerignore`). Отдаётся план сборки с командами — компилировать локально.
- **Telegram-бот.** Остаётся в дереве, из монолита не запускается: `aiogram`
  и `typer` не входят в `another/requirements.txt`. Workflow
  `admin-bot-deploy.yml` в монорепозиторий не переносился — он пушил образ
  бота в GHCR на каждое изменение `control-plane-admin/**`, что здесь только
  шум. Понадобится — восстановить из истории `another`.

## Свой домен в Cloudflare (когда появится)

`infra/cloudflare/` создаёт CNAME на воркер и гасит ECH (без этого ТСПУ видит
ECH-пакеты). Требует зоны, поэтому в CI не включён. И до включения надо
починить две вещи:

1. **Remote backend.** Сейчас state локальный: каждый прогон CI начинал бы с
   пустого state и заводил новый KV namespace. Нужен backend (R2/S3) либо
   вынести KV из Terraform совсем и оставить его за `wrangler` — второе проще
   и уже фактически сделано.
2. **Версия провайдера.** `main.tf` писался под `cloudflare/cloudflare ~> 4.41`
   и никогда не прогонялся через `terraform validate`. У провайдера были
   ломающие изменения между 4.x и 5.x — имена атрибутов надо перепроверить.

## Локальная разработка

Монолит целиком (как на HF, включая все остальные плагины):

```bash
cd cutaway
pip install -r requirements.txt -r another/requirements.txt
uvicorn main:app --reload --port 7860
# → http://127.0.0.1:7860/another/admin/
```

Только `another`, standalone (как `Dockerfile.api`) — админка окажется на
`/admin/`, потому что префикса нет; и то, и другое работает без правок:

```bash
cd another/control-plane-admin
python -m another_admin.api   # :8080
```

Воркер локально:

```bash
cd another/edge
cp ../.env.example .dev.vars   # оставить только ANOTHER_SERVICE_SECRET
npx wrangler dev
```
