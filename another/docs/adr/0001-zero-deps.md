# ADR 0001: Ноль внешних зависимостей в `core/` (v1) и исключение фазы 2

## Статус
Принято. **Исключение (фаза 2 / [ADR 0006](0006-pq-hybrid-identity.md)):**
`core/go.mod` содержит узкий список require:

| Пакет | Зачем | Кто импортирует |
|---|---|---|
| `github.com/cloudflare/circl` | ML-DSA-65 (FIPS 204) | `domain` идентичность |
| `github.com/refraction-networking/utls` | ClientHello-отпечаток Chrome | только `vless_reality.go` |
| `golang.org/x/crypto`, `golang.org/x/sys` | транзитивно utls/circl; HKDF/ChaCha для Reality | Reality handshake |

VLESS-WS по-прежнему на `crypto/tls` stdlib. gRPC не добавляли.

## Контекст
Сетевое окружение сборки v1 могло не иметь `proxy.golang.org`. Сейчас GOPROXY
доступен. Даже при этом мы не тащим xray-core / sing-box / gVisor.

## Решение v1 (сохраняется для WS и лимитеров)

| Было (черновик) | Стало | Почему |
|---|---|---|
| `golang.org/x/time/rate` | `internal/adapters/ratelimiter/token_bucket.go` | Свой token bucket. |
| `gorilla/websocket` | `internal/adapters/transport/wsproto/` | RFC 6455, ~250 строк. |

## Последствия
- Бинарник desktop/Android тянет uTLS даже если текущий узел — WS (линковка mux).
  Это плата за один composition root. Разделить `-tags reality` можно позже.
- `go.sum` теперь в репозитории. CI: Go 1.24+.
- gRPC по-прежнему заглушка: приоритет ниже xHTTP.
