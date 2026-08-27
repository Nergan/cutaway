# План доведения Another до рабочего состояния

Не календарный релиз и не «сделать за одну сессию». Критерий готовности
задаёт оператор. Этот документ — очередь работ так, чтобы следующий агент
не гадал приоритеты.

Связано: ответы аудита 2026-08-25, [principles.md](principles.md),
[infrastructure.md](infrastructure.md), [auth-spec.md](auth-spec.md),
[provisioning.md](provisioning.md), [circumvention.md](circumvention.md).

## Зафиксированные решения аудита

| # | Вопрос | Решение |
|---|---|---|
| A.1 | Web vs desktop админка | **Web.** Доступ нескольким людям. Не login+email — PQ-ключи ([auth-spec.md](auth-spec.md)). |
| A.2 | Прямой Mongo vs backend | **Отдельный backend API** (и он же mongo-прокси для Worker). |
| A.3 | Монитор / realtime | Поллинг, не стрим. Полные компактные логи с затиранием, сессии, пингер как список URL, 4xx `/auth`, алерты на злоупотребления. Квота — минута ок. |
| A.4 | Auth админки | Гибрид Ed25519+ML-DSA, ключ не в localStorage, seq-цепь; не блокчейн/ZKP из черновика. |
| B.5–7 | TOFU vs ключ в бинарнике | **Invite-bound TOFU.** Ключ в компиле отвергнут: хуже против шаринга и реверса. |
| B.8 | Автосборка | Кнопка в админке — да. Сайт самообслуживания (`/another/` + Actions) — да, [user-portal-plan.md](user-portal-plan.md). |
| C.9 | PQ | Да, для клиента и админа (подписи). Не как anti-tamper бинарника. |
| C.10 | Ротация | Переиздание в админке (revoke + новый invite). |
| D.11 | Atlas Data API | Self-hosted REST-прокси на HF/Render, нативный драйвер. |
| D.12 | VPS / Terraform | VPS пока нет. Готовить generic-модуль и сетку взаимного прокси. |
| D.13 | HF Spaces | **Основной compute**, риск ToS принят. Снаружи — через Worker. |
| D.14 | Render sleep | Пингер Worker. Мощность мала — только резерв. |
| E.15 | TUN / kill switch | Блокер. Делать, не «ручной прокси». |
| E.16 | Платформы | Win10/11, Linux широко, Android. Win7/8 best-effort. Без macOS/iOS в релизе. |
| E.17 | Reality | Обязателен в коде. В проде — когда будет IP. |
| E.18 | Flutter первым шагом | **Нет.** Сначала логика. Оператор прогоняет GUI у себя и даёт фидбек. |
| F.19 | Пробелы handoff §5 | Все остаются в бэклоге; порядок — ниже, не «всё сразу». |

Если какой-то ответ аудита был не про то — поправки внесены в документацию
явно (ключ в бинарнике, ZKP, «HF = вход», Windows XP).

## Фазы

Каждая фаза должна оставлять репозиторий согласованным (код + docs). Деплой
только по просьбе оператора.

### Фаза 0 — правда в документах и мёртвый Data API

Статус: **этот документ и связанные docs — сделаны в сессии аудита.**

Ещё в фазе 0, кодом, без деплоя:

- Пометить `edge/` Atlas Data API как мёртвый; порт репозитория пользователей
  перевести на HTTPS нашего прокси (скелет API + контракт).
- Не тащить `motor`. Telegram-бота не развивать; не ломать CLI, пока нет API.

### Фаза 1 — control plane, без которого ничего не коннектится

Статус: **сделано в коде (без деплоя), 2026-08-25.** Origin API в
`control-plane-admin/` (FastAPI + PyMongo Async): `/internal/v1/*` для Worker,
`/admin/v1/*` по [auth-spec.md](auth-spec.md), каркас Web на `/admin/`.
Worker ходит в `RestProxyUserRepository`. Pinger Cron читает список URL из API.
Capped `events`, коллекция `admins`, поля `public_key_mldsa65`.
Прогон: pytest 34/34, vitest 33/33, `npm run typecheck` чисто.

Ещё не деплоили. GUI вёрстки оператора не подключали. JS-админка тянет noble
с CDN для ML-DSA — проверить на машине оператора (интерп Python↔noble). CLI-путь
(`another-admin keygen`) самодостаточен и не зависит от noble.

### Фаза 2 — клиент как VPN, не как библиотека протоколов

Статус: **код без деплоя, 2026-08-26.** TUN + userspace NAT (IPv4 TCP/UDP),
kill switch (nftables / маршруты Windows / VpnService), xHTTP client+origin
sidecar, Reality-клиент (uTLS), пробник RTT, гибрид Ed25519+ML-DSA-65,
embed token+entrypoints (не private key). Worker проксирует `/xhttp`.

Не закрыто средой агента: Wintun.dll на живой Windows, nftables от root,
VpnService/gomobile, живой Reality-сервер (нет VPS — фаза 4). Dev:
`ANOTHER_ALLOW_NOOP_TUN=1`. Сборка инсталлятора из админки — фаза 3 (сделано).

### Фаза 3 — монитор, которым можно пользоваться

Статус: **код без деплоя, 2026-08-26.** Сессии (origin `sessions` + Worker
upsert при `/auth` и close при `/proxy`), 4xx `/auth` → `auth_fail` + детектор
аномалий, пороги и колокольчик в UI, переиздание и кнопка «Собрать»
(ldflags embed token+nodes, не private key). Terraform `infra/generic-vps/`
+ один Docker-образ HF/Render/VPS (`deploy/origin/Dockerfile`). Android:
`SetTunFd` + Kotlin MethodChannel в `app/native/android/` (gomobile — у
оператора). iOS вне релиза.

Не закрыто средой агента: живой `go build` инсталляторов (флаг
`ANOTHER_BUILD_ENABLED=1` у оператора), gomobile `.aar`, VpnService на
устройстве, `terraform validate` (нет registry).

### Фаза 4 — когда появится VPS

Статус: **сервер в коде + round-trip тест, прод ждёт IP (2026-08-26).**
`core/cmd/reality-origin`: Reality handshake (совместим с клиентом фазы 2) +
VLESS-exit + fallback на SNI-донора (probe видит чужой сайт). Полуавтомат:
`-probe host:443`. Полный скан подсети — внешний RealiTLScanner, не вендорим.
xHTTP на том же образе (`ANOTHER_RUN_XHTTP`). Terraform generic-vps
пробрасывает 443→8443. `TestRealityRoundTripEcho` зелёный.

Не закрыто: живой VPS, подбор донора в той же AS, деплой, замеры ТСПУ.

### Вне фаз, по фидбеку оператора

- Прогон Flutter (`flutter create` / analyze / test) — **у оператора**,
  список падений присылается агенту. Не первый шаг.
- GUI клиента полировать после TUN.
- iOS/macOS.
- Hysteria2 как ещё один адаптер порта.
- Windows XP — не планировать, пока не будет отдельного решения «заморозить
  ископаемый toolchain»; скорее всего никогда.

## Пробелы handoff §5 — куда легли

| # | Пробел | Фаза |
|---|---|---|
| 1 TUN | 2 | |
| 2 Kill switch | 2 | |
| 3 Нативный мост Android | 3 (iOS вычеркнут из релиза) | |
| 4 Flutter platform-папки | у оператора, не блокер логики | |
| 5 VLESS-Reality | 2 код / 4 прод | |
| 6 VLESS-gRPC | после xHTTP, низкий | |
| 7 Terraform validate | 3, среда оператора | |
| 8 Деплой Worker | когда оператор скажет | |
| 9 Реальный Atlas | оператор; Data API не использовать | |
| 10 Push-инвалидация бана | 1 (прокси может ещё и дернуть KV) | |
| 11 Батч квоты | оставить минутный, низкий | |
| 12 motor в боте | **не делать**; бот снимается, Async PyMongo в API | |
| 13 flutter analyze | оператор | |

## TODO, которые агент не может закрыть в своей среде

Писать в README компонента, не молчать:

- Flutter SDK / pub.dev: `flutter create --platforms=windows,linux,android`,
  analyze, test, прислать лог.
- Android SDK + gomobile: сборка `.aar`, VpnService.
- Wintun.dll на реальной Windows, nftables на реальном Linux.
- Terraform registry, wrangler к реальному аккаунту — только после «можно деплоить».
- Замеры ТСПУ на конкретных провайдерах круга (это не юнит-тест).

## Порядок, если времени мало

Developer-blocking: **D.11 mongo-прокси → идентичность/enroll живы → TUN →
вход CF+HF → Reality/xHTTP**. Админ-монитор параллелится с фазы 1, но не вместо
TUN. Вёрстка админки — после API.
