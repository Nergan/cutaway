# План реализации

Проект реализуется по частям (см. обсуждение в docs/architecture.md, §0).
Каждая часть — самостоятельно проверяемый результат (сборка/тесты проходят),
а не просто "написанный текст кода".

## Part 1 — Go Core ✅ done

- Гексагональная архитектура: `domain`/`ports`/`adapters`/`app` (use-cases).
- Идентичность устройства на Ed25519 (замена сломанного MAC-based HWID).
- Собственная реализация VLESS wire-format (`vlessproto`) — сверена с
  исходниками xray-core, не заимствована (лицензии MPL-2.0/GPL-3.0 не переходят).
- Собственный минимальный WebSocket-клиент RFC 6455 (`wsproto`) — нулевая
  внешняя зависимость вместо `gorilla/websocket` (которая тянет `golang.org/x/net`,
  недоступный в нашем сетевом окружении сборки).
- Рабочий `VLESSWebSocketTransport` (Tier1): TLS (stdlib) → WS-хендшейк →
  VLESS-заголовок.
- HTTP challenge-response аутентификация к control-plane.
- Failover-логика (`ConnectUseCase`) с юнит-тестами на моках.
- Kill switch и TUN — логика координации реализована; платформенные
  адаптеры (WFP/VpnService/NetworkExtension/pf/nftables, Wintun/utun/
  VpnService-fd) — задокументированные заглушки (TODO v2), т.к. требуют
  Android SDK/Xcode/root-привилегий, недоступных в этой среде.
- Верификация: `gofmt`, `go vet`, `go test` — все зелёные;
  кросс-компиляция под windows/darwin/linux (amd64+arm64)/android — ✅,
  ios — ограничение toolchain (требует реальный macOS+Xcode).
- `Dockerfile`, `.dockerignore`, `README.md` для `core/`.

## Part 2 — Edge (Cloudflare Worker) ✅ done

- `/enroll`, `/nonce`, `/auth`, `/proxy` хендлеры (TypeScript), гексагональная
  архитектура (`domain`/`ports`/`adapters`/`handlers`), 0 рантайм-зависимостей
  (все npm-пакеты — только devDependencies).
- Durable Object как nonce-леджер (anti-replay, строгая консистентность —
  исправление уязвимости Cache API из исходного черновика).
- Workers KV как cache-aside для бан-листа/квоты и как session store
  (закрывает архитектурный пробел, обнаруженный при реализации: session_token
  сам по себе непрозрачен, без сохранённого состояния его нечем было
  валидировать на data-plane — см. `SessionStorePort`).
- `/proxy` — реальный VLESS-WS шлюз через Cloudflare TCP Sockets API
  (`connect()` из `cloudflare:sockets`), не заглушка.
- MongoDB Atlas Data API адаптер (HTTPS, не TCP-драйвер — недоступен из
  V8-изолята).
- Ed25519-верификация через нативный WebCrypto (`crypto.subtle`), без
  сторонней крипто-библиотеки — подтверждено, что Workers это поддерживают.
- Golden-тест совместимости VLESS wire-format: байты сгенерированы реальным
  `go run` поверх Go-энкодера, TS-парсер декодирует их и сверяется побайтово.
- Верификация: `tsc --noEmit` (два прохода), `vitest` — 30/30 тестов,
  `wrangler deploy --dry-run` — бандлится и резолвит все биндинги.
- `wrangler.toml`, `package.json`, `README.md` для `edge/`.

## Part 3 — Control-plane admin (Python) ✅ done

- CLI (Typer): `another-admin invite/revoke/list/report`.
- Telegram-бот (aiogram): `/invite`, `/devices`, `/revoke`, `/report` —
  второй driving-адаптер тех же domain-сервисов, что и CLI.
- Гексагональная архитектура: `domain/` → `ports/` (typing.Protocol) →
  `adapters/` (MongoDB через pymongo, Telegram через httpx, QR-генерация).
- Верификация: `pytest` — 19/19 тестов, включая тесты Mongo-адаптера через
  `mongomock`.
- Найдено и исправлено по ходу реализации: (1) `mongomock` не поддерживает
  positional projection MongoDB — адаптер переписан без неё; (2) транслитерация
  комментариев в client_id не работала для кириллицы — добавлена таблица
  транслитерации (пример "Друг из Питера" из §10 спецификации иначе
  схлопывался бы в бессмысленный `device-<hex>`).
- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `Dockerfile`
  (для бота), `README.md`.

## Part 4 — Flutter GUI ✅ done

- Гексагональная архитектура: `domain/` (entities, ports) → `application/`
  (use-cases) → `infrastructure/` (HTTP/MethodChannel/secure storage
  адаптеры) → `presentation/` (AppState + 4 экрана + 2 виджета).
- UI только на английском (по требованию).
- `HttpCoreAdapter` (десктоп) — реальный клиент к control API `core/`.
- `PlatformChannelCoreAdapter` (мобильные) — задокументированная правка
  относительно спецификации: MethodChannel + gomobile bind вместо сырого
  dart:ffi (см. `app/README.md`).
- `ConfigRepositoryHttpAdapter` — прямой HTTP к `edge/enroll`.
- 19 pure-Dart unit-тестов (`test/domain/`).
- **По ходу работы найден и исправлен реальный баг в `core/`**: устройство
  должно сгенерировать публичный ключ ДО того, как узнает свой серверный
  client_id (из ответа `/enroll`), а `KeyStorePort` был параметризован
  именно client_id — ключ, отправленный в `/enroll`, физически не совпадал
  бы с ключом при первом `/auth`. Исправлено в `core/` (идентичность больше
  не индексируется по client_id), добавлены `GET /identity`, `POST /switch`
  и регрессионный тест. Все тесты Go и кросс-компиляция под 6 платформ
  перепроверены после рефакторинга — по-прежнему зелёные.
- **Честно не верифицировано**: `flutter analyze`/`flutter test` — нет
  Flutter SDK и доступа к pub.dev в среде разработки (проверено — оба
  хоста в 403). Сделана грубая автоматическая проверка баланса скобок по
  всем `.dart`-файлам + валидация `pubspec.yaml` как YAML.
- `pubspec.yaml`, `app/README.md` с точным списком TODO для реального
  Flutter-окружения (`flutter create`, нативный код-мост).

## Итог v1 и что дальше

Части 1–5 по старому плану реализованы в том объёме, который позволяла среда.
Это **не** «доведено до релиза». Аудит 2026-08-25 зафиксировал новый замысел и
очередь: [release-plan.md](release-plan.md), карта документов — [README.md](README.md).

Код, который в v1 зелёный, остаётся базой. Со скоупа релиза сняты: Telegram-бот,
iOS/macOS как цель, Atlas Data API, ключ устройства в бинарнике. Обязательны:
Web-админка, REST-прокси к Mongo, TUN/kill switch, Reality+xHTTP, PQ-гибрид,
HF как основной origin.

Честно неверифицированное (Flutter, Terraform, Xcode, живой Atlas/Docker в
песочнице агента) по-прежнему не выдаётся за прогнанное. Прогон GUI — у
оператора, не первый шаг агента.

## Фаза 4 — Reality-origin (код, без деплоя)

- `cmd/reality-origin`: handshake + VLESS-exit + fallback на dest.
  Round-trip (`TestRealityRoundTripEcho`) зелёный.
- `-keygen`, `-probe host:443`. RealiTLScanner — внешний инструмент.
- Образ `deploy/origin` собирает `reality-origin`; флаг `ANOTHER_RUN_REALITY`.

## Фаза 3 — монитор (код, без деплоя)

- Origin: коллекция `sessions`, ops `sessions` / `evaluate_alerts` /
  `alert_thresholds_*` / `build_installer` / investigation.
- Worker: 4xx `/auth` → `auth_fail`; успешный `/auth` → upsert сессии (hash IP);
  конец `/proxy` → close.
- UI `/admin/`: сессии, колокольчик, Reissue + «Собрать».
- Образ `deploy/origin/Dockerfile` (HF = Render = generic VPS).
- Android-клей `app/native/android/` + `SetTunFd` в mobilelib.
- pytest 44/44, vitest 36/36, `tsc --noEmit` чисто (2026-08-26).

## Фаза 2 — VPN-клиент (код, без деплоя)

- TUN + userspace NAT (`internal/adapters/netstack`), kill switch, mux транспортов.
- xHTTP: клиент и `cmd/xhttp-origin`; Worker reverse-proxy `/xhttp`.
- Reality-клиент (uTLS). PQ-идентичность circl ML-DSA-65.
- Тесты: `go test ./...` зелёные (2026-08-26), `go vet` чисто.

## Фаза 1 — origin API + REST-прокси (код, без деплоя)

- FastAPI в `control-plane-admin/another_admin/api/`: Worker `/internal/v1`,
  админ `/admin/v1` (гибрид Ed25519+ML-DSA-65, seq/chain), каркас `/admin/`.
- Worker: `RestProxyUserRepository`, Cron-pinger по списку URL, `/health`,
  `/internal/ban-invalidate`.
- CLI: `keygen`, `admin-register`, `reissue`.
- Тесты (2026-08-25): pytest 34/34, vitest 33/33, `npm run typecheck` чисто.

## Part 5 — Infra + CI/CD ✅ done (как код v1)

- `infra/cloudflare/` — Terraform: KV namespace для бан-кэша, DNS-запись
  маршрута к Worker'у, отключение ECH (§9.3). Осознанно НЕ управляет
  деплоем самого кода Worker'а — это делает `wrangler deploy`
  (bundling+upload), Terraform — только инфраструктура вокруг него.
- `.github/workflows/`:
  - `core-ci.yml` — gofmt/vet/test + кросс-компиляция под 6 платформ на
    каждый push/PR, затрагивающий `core/`.
  - `edge-ci.yml` — typecheck (2 прохода) + vitest + `wrangler --dry-run`.
  - `edge-deploy.yml` — то же + реальный `terraform apply` → `wrangler deploy`
    на push в `main`.
  - `admin-ci.yml` — pytest + проверка, что CLI entry point реально работает.
  - `admin-bot-deploy.yml` — сборка и публикация Docker-образа бота в ghcr.io.
  - `app-ci.yml` — `flutter analyze`/`flutter test` (не верифицировано
    локально, см. `app/README.md`).
- Финализирован `docker-compose.yml` — все три локальных сервиса (mongo,
  core, admin-bot) на месте, с пояснениями, почему edge/ и app/ туда не
  входят (Workers — не контейнерный рантайм; Flutter — не сервис).
- **Честно не верифицировано**: Terraform не прогонялся через
  `terraform validate`/`plan` (нет доступа к `registry.terraform.io` —
  проверено, `403 host_not_allowed`; terraform CLI не установлен). Все
  `.tf`-файлы прошли грубую проверку баланса скобок; все `.yml`-файлы
  (workflows + docker-compose) синтаксически провалидированы через
  `yaml.safe_load`, но сами пайплайны не запускались на реальном раннере.

v1 по пяти частям остаётся в дереве и зелёная там, где её прогоняли. К рабочему
состоянию для закрытого круга это не равно — см. блок «Итог v1 и что дальше»
выше и [release-plan.md](release-plan.md).