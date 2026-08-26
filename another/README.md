# Another VPN

**Another** — «ещё один» / «другой» VPN: приватный, для закрытого круга, не
публичный продукт. Go-ядро + Flutter GUI + Cloudflare Worker как вход +
Hugging Face Space как основной origin + MongoDB Atlas. Принципы:
кроссплатформенность и скорость — [docs/principles.md](docs/principles.md).

Документация — источник истины по замыслу. Начните с
[docs/README.md](docs/README.md).

UI клиента — английский. Документация и комментарии в коде — русские.

## Статус

v1 по частям 1–5 **написана**. Фазы 0–4 в коде, без деплоя. Reality-сервер
есть; в проде — когда появится VPS. Очередь: [docs/release-plan.md](docs/release-plan.md).

| Часть | Компонент | Код v1 | К релизу |
|---|---|---|---|
| 1 | `core/` Go-ядро | TUN/NAT, xHTTP, Reality клиент+сервер, PQ | живой Wintun/nft; Reality на VPS когда будет IP |
| 2 | `edge/` Worker | REST-прокси, pinger, тесты зелёные | деплой только по просьбе |
| 3 | `control-plane-admin/` | CLI + origin API + монитор `/admin/` | бот не развивать; GUI-вёрстки — позже |
| 4 | `app/` Flutter | Dart написан, SDK не прогонялся | не первый шаг; оператор тестирует у себя |
| 5 | `infra/` Terraform/CI | написано, terraform не прогонялся | модуль generic VPS, без деплоя пока |

## Структура

```
another/
├── core/                      # Go-ядро
├── edge/                      # Cloudflare Worker
├── control-plane-admin/       # Python CLI + origin API (+ бот в дереве, вне релиза)
├── app/                       # Flutter GUI
├── infra/                     # Terraform Cloudflare
├── docs/                      # спецификация и план — см. docs/README.md
├── docker-compose.yml
├── .env.example
└── .gitignore                 # секреты, сборки, docs/private/; не сами docs/*.md
```

## Быстрый старт (локально, не прод)

```bash
cp .env.example .env
cd core
go run ./cmd/desktop
```

Деплой облака — только когда оператор явно попросит.

## Лицензии референсов

VLESS реализован сами ([ADR 0002](docs/adr/0002-vless-reimplementation.md)):
анализ `xray-core`/`sing-box`, без копирования кода.
