# `control-plane-admin/` — CLI + origin API (фаза 3)

CLI (Typer) — аварийный канал и keygen. FastAPI origin — REST-прокси для
Worker (`/internal/v1`) и админ-API (`/admin/v1`, [auth-spec.md](../docs/auth-spec.md)).
Web-монитор: `/admin/` (сессии, алерты, invite/reissue). Публичный портал
инсталлятора: `/` (на Space — `/another/`). Telegram-бот в дереве, **не развивается**.

PyMongo **Async** в API, не `motor`. Синхронный pymongo остаётся в CLI.

## Запуск origin API (локально)

```bash
cd control-plane-admin
pip install -r requirements-dev.txt
pip install -e .
export MONGO_URI=mongodb://127.0.0.1:27017
export ANOTHER_SERVICE_SECRET=dev-secret
python -m another_admin.api
# http://127.0.0.1:8080/health
# http://127.0.0.1:8080/          портал (код → zip)
# http://127.0.0.1:8080/admin/    админка
```

Первый админ:

```bash
another-admin keygen --admin-id root --output ./root.another-admin-key --register
# passphrase спросит сам; файл не коммитить
```

## Статус верификации

```
pip install -r requirements-dev.txt                            → ok (cryptography 48, fastapi, pymongo async)
pytest -v                                                      → 57/57 зелёные (2026-08-27), вкл. portal/redeem/jobs
another-admin --help                                           → invite/revoke/list/report/reissue/keygen/admin-register
```

Реального MongoDB/Docker в среде разработки не было (см.
`docs/implementation-plan.md`, тот же класс ограничений, что и в Part 1) —
адаптер `MongoUserRepository` протестирован через `mongomock`
(эмулирует API `pymongo` в памяти), что покрывает реальную логику запросов
(вставка, поиск, обновление с позиционным фильтром), а не только
domain-логику на fake-репозитории.

## Находка в процессе тестирования

`mongomock` не поддерживает positional projection MongoDB (`"clients.$": 1`),
хотя настоящий MongoDB/Atlas её поддерживает штатно. Вместо того чтобы
подстраивать тесты под ограничение мок-библиотеки, `find_client` в
`adapters/mongo_repository.py` переписан без positional projection —
получает документ целиком и фильтрует нужного клиента в Python. Это и
проще, и одинаково корректно работает против mongomock и настоящего
MongoDB/Atlas — на документах такого размера (один пользователь, единицы
устройств) разница в трафике незначительна.

Отдельно: транслитерация комментария в `client_id` (`_slugify`) изначально
не работала для кириллицы — `unicodedata.normalize("NFKD", ...)`
раскладывает только диакритику на латинице (é → e + акцент), а не разные
алфавиты. Добавлена явная таблица транслитерации кириллицы — без неё
пример из §10 спецификации ("Друг из Питера") схлопывался бы в
`device-<hex>` вместо `drug-iz-pitera-<hex>`.

## Использование

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .   # даёт команду `another-admin` в PATH

export MONGO_URI="mongodb://localhost:27017"   # см. ../docker-compose.yml (сервис mongo)
export MONGO_DB_NAME=another
export ANOTHER_CONTROL_PLANE_URL=https://cf-worker.another.example

another-admin invite --comment "Друг из Питера" --quota-gb 50
another-admin list
another-admin report
another-admin revoke --client-id drug-iz-pitera-a1b2c3
```

### Telegram-бот

```bash
export TELEGRAM_BOT_TOKEN="..."          # см. .env.example
export TELEGRAM_ADMIN_IDS="123456789"    # ваш Telegram user_id, через запятую если несколько

python -m another_admin.bot.main
# в Telegram: /invite <комментарий>, /devices, /revoke <client_id>, /report
```

Либо через Docker:

```bash
docker build -t another-admin-bot control-plane-admin/
docker run --env-file .env another-admin-bot
```

## Осознанные упрощения v1

| Место | Упрощение | Комментарий |
|---|---|---|
| `bot/main.py` | Синхронный `pymongo` внутри асинхронных aiogram-хендлеров | Бот вне релиза; origin API использует PyMongo Async. Не тащить `motor`. |
| CLI `revoke` | Не дергает `POST /internal/ban-invalidate` | Origin API после revoke/reissue делает push, если задан `EDGE_INTERNAL_URL`. CLI — аварийный канал, бан подхватится по TTL 30 с. |
| `adapters/mongo_repository.py` | Один invite = один новый документ пользователя | Не поддерживает сценарий "добавить второе устройство существующему пользователю" — TODO v2. |

## Тесты

```bash
pytest -v
```

Три уровня, как и в `core/` (Go) и `edge/` (TS):
- `test_device_provisioning_service.py`, `test_quota_report_service.py` — domain-логика на fake-репозитории (Protocol, без единой библиотеки моков).
- `test_mongo_repository.py` — реальные MongoDB-запросы через `mongomock`.
- `test_qr_generator.py` — чистая функция-утилита.
