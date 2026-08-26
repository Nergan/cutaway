# `edge/` — Cloudflare Worker (control-plane + Tier1 data-plane)

Гексагональная архитектура: `domain/` → `ports/` → `adapters/` (Durable Object, KV,
REST-прокси к origin API, WebCrypto) → `handlers/` → `index.ts`.

Worker не ходит в Atlas Data API (EOL 2025-09-30). Реализация —
`src/adapters/rest_proxy_user_repository.ts` → origin
`POST/GET /internal/v1/...` с заголовком `X-Another-Proxy-Secret`.
Старый `mongo_atlas_user_repository.ts` оставлен как мёртвый артефакт v1.

## Статус верификации (v1)

```
npm install                                    → ok, 0 критичных для рантайма зависимостей
                                                   (все внешние пакеты — только devDependencies:
                                                   typescript, vitest, wrangler)
npm run typecheck                              → чисто (два прохода: строгий src-only
                                                   без Node-типов + отдельный для тестов)
npm test (vitest)                              → 33/33 тестов зелёные (2026-08-25, + rest_proxy)
npx wrangler deploy --dry-run                  → бандлится успешно, биндинги (Durable
                                                   Object, KV, vars) резолвятся корректно
```

Отдельно отмечу: тест `test/vless_protocol.test.ts` содержит **golden-вектор**,
сгенерированный реальным `go run` поверх той же логики, что в
`core/internal/adapters/transport/vlessproto/vless.go` — TS-парсер проверяется
на совместимость с байтами, которые реально произвела Go-реализация, а не
только на самосогласованность.

## Ключевое исправление относительно черновика спецификации

Nonce-леджер (anti-replay) реализован через **Durable Object**
(`adapters/durable_object_nonce_store.ts`), а не через Cloudflare Cache API,
как предлагал исходный черновик — см. `docs/architecture.md` §0.1, правка #2,
и комментарий в `src/ports/nonce_store_port.ts`. Cache API не даёт глобальной
консистентности между дата-центрами, что делает anti-replay защиту
проходимой; Durable Object даёт строгую консистентность за счёт единого
объекта-владельца.

## Архитектурный пробел, закрытый в процессе реализации

Исходная спецификация не уточняла, как `session_token`, выданный `/auth`,
на самом деле авторизует последующее WebSocket-подключение к `/proxy` —
токен сам по себе непрозрачен (случайные байты). Добавлен
`SessionStorePort`/`KvSessionStore` (`src/ports/session_store_port.ts`):
токен сохраняется в KV с TTL 120с при выдаче и сверяется в `handlers/proxy.ts`
перед апгрейдом WebSocket. См. `docs/implementation-plan.md`.

## Локальный запуск (dev)

```bash
cd edge
npm install
cp ../.env.example .dev.vars   # wrangler dev читает секреты отсюда
                                # нужны MONGO_REST_PROXY_URL и ANOTHER_SERVICE_SECRET
npm run dev                    # поднимет wrangler dev на localhost
```

Origin API должен быть запущен (`python -m another_admin.api`, порт 8080),
иначе `/enroll` и `/auth` не найдут клиента. Domain-логика по-прежнему
изолированно: `npm test`.

## Деплой (после заполнения секретов)

```bash
npx wrangler kv namespace create BAN_CACHE   # получить id, вписать в wrangler.toml
npx wrangler secret put ANOTHER_SERVICE_SECRET
npx wrangler deploy
```

Отдельно нужно отключить ECH через Cloudflare API (§9.3 спецификации) —
в v1 делается вручную/через `curl`, автоматизация через Terraform — Part 5.

## Известные упрощения v1 (документированы в коде)

| Место | Упрощение | Комментарий |
|---|---|---|
| `handlers/proxy.ts` | Учёт трафика (`incrementUsage`) — раз в конце соединения, а не потоковый Durable Object-счётчик из §8.4 спецификации | Приемлемо для типичных VPN-сессий (минуты-часы); для очень долгих сессий — TODO v2 |
| `wrangler.toml` | Один KV namespace на бан-кэш и session store (разные префиксы ключей) | Не критично для масштаба "закрытая группа"; разделить на два namespace — тривиально при необходимости |
| `adapters/webcrypto_ed25519_verifier.ts` | Нет — полностью рабочая реализация | Ed25519 в WebCrypto подтверждён нативно поддерживаемым в Workers |
| VLESS-WS early data (`?ed=2048`) | Не реализовано | Оптимизация "нулевого RTT" из референсных CF-Workers-VLESS проектов, экономит один round-trip; функциональность не страдает без неё |

## Что НЕ реализовано (см. `docs/architecture.md`)

- Отзыв ключа устройства (`revoke_device`, §7.3) — логика `KvBanCache.invalidate()`
  готова, но не подключена ни к одному admin-хендлеру (это будет
  `control-plane-admin/`, Part 3).
- Динамический список узлов по геолокации запроса (`request.cf`) — сейчас
  статический `NODES_JSON`.
