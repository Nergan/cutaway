# `core/` — Go-ядро VPN-клиента «Another»

Кроссплатформенное сетевое ядро, гексагональная архитектура (domain/ports/adapters).
См. корневой [README.md](../README.md) и [docs/architecture.md](../docs/architecture.md) для контекста всего проекта.

## Статус верификации (v1)

```
gofmt -l .        → чисто
go vet ./...      → чисто
go test ./...     → все тесты зелёные
go build ./...    → успешно для нативной платформы

Кросс-компиляция:
  windows/amd64  ✅
  darwin/amd64   ✅
  darwin/arm64   ✅
  linux/amd64    ✅
  linux/arm64    ✅
  android/arm64  ✅
  ios/arm64      ⚠️  требует clang/Xcode toolchain (недоступен вне macOS —
                     ожидаемое ограничение платформы, не баг кода)
```

Ноль внешних зависимостей в v1; фаза 2 добавила circl + utls
(см. `docs/adr/0001-zero-deps.md`).

## Что работает в фазе 2 (код, без деплоя / без root в CI)

| Компонент | Файл | Статус |
|---|---|---|
| Гибрид Ed25519+ML-DSA-65 | `internal/domain/identity.go` | ✅ тесты |
| Userspace NAT IPv4 TCP/UDP | `internal/adapters/netstack/` | ✅ тесты (memory TUN) |
| Linux `/dev/net/tun` | `internal/adapters/tun/linux_tun.go` | код; нужен CAP_NET_ADMIN |
| Windows Wintun | `internal/adapters/tun/windows_tun.go` | код; нужен `wintun.dll` рядом с exe |
| Android fd от VpnService | `internal/adapters/tun/android_tun.go` | код; gomobile `.aar` — у оператора, клей в `app/native/android/` |
| Kill switch nft/routes | `internal/adapters/killswitch/` | код; noop если `ANOTHER_ALLOW_NOOP_TUN=1` |
| VLESS-xHTTP | `vless_xhttp.go` + `cmd/xhttp-origin` | клиент+origin sidecar |
| VLESS-Reality клиент | `vless_reality.go` (uTLS) | ✅ |
| VLESS-Reality сервер | `reality_server.go` + `cmd/reality-origin` | ✅ round-trip тест; прод — когда будет IP |
| Пробник RTT | `internal/adapters/probe/` | ✅ |
| Embed token+nodes | `internal/adapters/provisioning/` | ldflags, не private key |

Dev без прав: `ANOTHER_ALLOW_NOOP_TUN=1` (тогда это снова «библиотека протоколов», не VPN).

## Что реально работает в v1

| Компонент | Файл | Статус |
|---|---|---|
| Идентичность устройства (Ed25519, без MAC/HWID) | `internal/domain/identity.go` | ✅ реализовано |
| Failover между узлами | `internal/app/connect_usecase.go` | ✅ реализовано + тесты |
| VLESS wire-format | `internal/adapters/transport/vlessproto/` | ✅ реализовано + тесты, сверено с исходниками xray-core |
| Минимальный WebSocket-клиент (RFC 6455) | `internal/adapters/transport/wsproto/` | ✅ реализовано + тесты |
| VLESS-over-WebSocket транспорт (Tier1) | `internal/adapters/transport/vless_ws.go` | ✅ реализовано (TLS через stdlib, без uTLS-мимикрии — см. ниже) |
| HTTP challenge-response аутентификация | `internal/adapters/auth/http_challenge.go` | ✅ реализовано + тесты |
| Файловое key storage (dev-grade) | `internal/adapters/keystore/file_keystore.go` | ✅ реализовано + тесты |
| Token bucket rate limiter | `internal/adapters/ratelimiter/token_bucket.go` | ✅ реализовано + тесты |
| Kill switch (state machine, координация) | `internal/domain`, `internal/app` | ✅ логика реализована |
| Локальный control API (для Flutter) | `cmd/desktop/main.go` | ✅ реализовано |
| gomobile-совместимый биндинг | `cmd/mobilelib/binding.go` | ✅ код готов, сборка `.aar`/`.xcframework` требует gomobile tool (недоступен в этой песочнице) |

## Что ещё заглушка после фазы 2

| Компонент | Почему |
|---|---|
| VLESS-gRPC | Ниже приоритетом, чем xHTTP; google.golang.org/grpc. |
| Reality **сервер** | Код и round-trip есть. Живой IP/донор — у оператора, без деплоя из агента. |
| macOS/iOS TUN | Вне релиза (ADR 0007). |
| Живой Wintun/nft в CI | Нет драйвера/root в агенте. |
| Кнопка сборки инсталлятора | Сделано в фазе 3 (admin op `build_installer`). |

## Локальный запуск (dev)

```bash
cd core
cp ../.env.example .env
# без админа:
#   ANOTHER_ALLOW_NOOP_TUN=1
go run ./cmd/desktop
# VPN (перехват TUN), не один dest:
curl -X POST http://127.0.0.1:47821/connect -d '{}'
curl http://127.0.0.1:47821/status
# origin xHTTP sidecar:
go run ./cmd/xhttp-origin
# Reality origin (локально, без публичного IP):
go run ./cmd/reality-origin -keygen
# ANOTHER_REALITY_PRIVATE_KEY=... ANOTHER_REALITY_DEST=www.microsoft.com:443 \
#   ANOTHER_REALITY_SHORT_IDS=aabbccdd ANOTHER_REALITY_SERVER_NAMES=www.microsoft.com \
#   go run ./cmd/reality-origin
go run ./cmd/reality-origin -probe www.microsoft.com:443
```

Без реального Cloudflare Worker (`edge/`, см. Part 2) `/connect` не подключится
ни к одному узлу — это ожидаемо для изолированного запуска ядра. Для
сквозного теста use-case логики без сети используйте `go test ./internal/app/...`
(там всё гоняется на `EchoTransport`, см. `internal/adapters/transport/echo_transport.go`).

## Правка при интеграции с Flutter (Part 4)

При проектировании онбординга в GUI обнаружился реальный порядок-зависимый
баг: `KeyStorePort.LoadOrCreateDeviceIdentity` изначально принимал
`clientID` и использовал его как имя файла ключа — но устройство узнаёт
свой серверный `client_id` только ИЗ ответа `/enroll`, а публичный ключ
нужно отправить В `/enroll` раньше. Ключ, сгенерированный "вслепую" до
онбординга, и ключ, используемый позже при первом `/auth` (уже под
настоящим client_id), физически не совпадали бы. Исправлено: идентичность
устройства больше не индексируется по client_id — один фиксированный слот
хранения на инсталляцию (`identity.seed`), а серверный `client_id`
передаётся отдельным параметром именно туда, где он используется — в тело
запроса `/auth` (`AuthPort.ChallengeResponse(ctx, node, clientID, identity)`).
Добавлен регрессионный тест
(`TestFileKeyStore_PublicKeyGeneratedBeforeEnrollmentMatchesLaterUse`).

Заодно добавлены: JSON (де)сериализация `NodeDescriptor`/`Tier`/`TransportKind`
(нужна для передачи списка узлов от `edge/enroll` через Flutter в Core),
`GET /identity` в `cmd/desktop` и `GetPublicKey()` в `cmd/mobilelib` (получить
публичный ключ до онбординга), и возможность передавать `client_id`/`nodes`
динамически в `POST /connect` вместо жёстко зашитых при старте процесса
значений из `.env`.
