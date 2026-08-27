# План: портал `/another`, инвайт-код, инсталлятор, монитор

**Статус: реализовано** (тот же агент, 2026-08-27). Ниже — исходное ТЗ, его не
переписывать под код: расхождения смотреть в `public_routes.py`,
`.github/workflows/another-installer-build.yml`, `core/cmd/desktop`.

**Автор плана: Cursor Grok 4.6.**

Связано: [provisioning.md](provisioning.md), [adr/0004-invite-bound-tofu.md](adr/0004-invite-bound-tofu.md), [release-plan.md](release-plan.md) (пункт B.8), [auth-spec.md](auth-spec.md) §4, [GETTING-STARTED.md](../GETTING-STARTED.md), [DEPLOY.md](../DEPLOY.md).

---

## 1. Целевой сценарий (как должен выглядеть продукт)

Оператор и пользователь могут быть одним человеком. Цикл один и тот же.

1. Оператор в админке (`/another/admin/`) жмёт **Invite**, получает одноразовый код (`enrollment_token`). Отправляет его человеку (мессенджер, лично). Токен в Mongo не хранится, только SHA-256; показать можно один раз.
2. Человек открывает **`https://nargan-projects.hf.space/another`** — это **публичная витрина**, не админка. Вводит код, выбирает платформу (для первого среза достаточно Windows amd64). Ждёт сборку, **скачивает установщик**.
3. Ставит как обычное приложение, запускает. Приложение само: рожает ключи устройства, делает `POST /enroll` на воркер, поднимает VPN (TUN + kill switch). Curl, PowerShell и `go build` у пользователя нет.
4. Оператор на мониторе видит устройство **ENROLLED**, затем активную сессию, `AUTH_OK`, трафик (трафик по-прежнему пишется при закрытии сессии — это не чинить в этом плане, только не врать в UI).

Админка остаётся отдельным замком (файл ключа + passphrase). Публичный портал **не** должен редиректить на `/admin/`.

---

## 2. Что уже есть vs чего нет

Это **не** новый продукт с нуля. Модель доступа уже принята: invite-bound TOFU, приватный ключ в exe **не** кладём ([ADR 0004](adr/0004-invite-bound-tofu.md), [provisioning.md](provisioning.md)).

| Кусок | Сейчас | Надо |
| --- | --- | --- |
| Invite | Админка `op: invite`, TTL 24ч, токен один раз | Не ломать. Портал **не** создаёт invite сам |
| `/another/` | `RedirectResponse` на `/admin/` в `another_admin/api/app.py` | Отдавать публичную страницу |
| Кнопка Build | `op: build_installer` **reissue** (банит текущий client_id) + печатает `go build -ldflags`, `compiled: false` | Для **нового** инвайта портал **не** делает reissue. Сборка должна давать скачиваемый файл |
| ldflags embed | `provisioning/embed.go`: token, client_id, nodes, build_id | Оставить. Это правильный контракт |
| Автоэнролл в ядре | `cmd/desktop` **читает** embed, **не вызывает** `/enroll`. Connect ждёт внешний curl | Первый запуск: identity → enroll → connect как VPN |
| GUI пользователя | Flutter в `app/` без сгенерированных `windows/`/`android/`, SDK в этой среде нет | **Не блокер среза.** Срез = Windows exe (+ wintun), который сам коннектится. Трей/окно — желательно; Flutter — следующая итерация |
| Сборка на Space | `.dockerignore` выкидывает `another/core`; Go в образе монолита нет; `ANOTHER_BUILD_ENABLED` выключен | **Не компилировать на Hugging Face.** Диск эфемерный, нет тулчейна, таймауты |
| Монитор | Устройства, сессии, события, `AUTH_OK` уже пишутся воркером | После автоэнролла и полного VPN данные сами появятся. Не плодить второй монитор |

В [provisioning.md](provisioning.md) и [release-plan.md](release-plan.md) B.8 прямо сказано: кнопка сборки в админке — да, **сайт самообслуживания — нет, «на будущее»**. Этот план **расширяет скоуп**: сайт самообслуживания входит в работу. Следующий агент обязан поправить ADR 0004 / provisioning / release-plan одной короткой правкой («было будущее, стало срез N»), а не делать вид, что так было всегда.

Прогон GETTING-STARTED (curl + `dest_host=example.com`) доказал control plane и `/auth`. Это **смоук одного потока**, не «поставь приложение». Полный VPN по-прежнему: без `dest_host`, без `ANOTHER_ALLOW_NOOP_TUN`, админские права, `wintun.dll`.

Локально в рабочей копии на момент плана уже могут лежать **незакоммиченные** правки ядра/админки (отказ dial на `:8787`, пустой `client_id`, `edge_ban_invalidate` как `ops`, не `anomaly`). Их нельзя потерять: либо влить в ту же ветку, либо закоммитить отдельно до большой работы.

---

## 3. Жёсткие решения (не развилка «на вкус агента»)

Следующий агент **не** пересматривает TOFU и **не** кладёт приватный ключ в бинарник.

### 3.1. Где компилировать

**GitHub Actions**, не Space и не браузер пользователя.

Почему не Space: нет Go в runtime-образе, `another/core` сознательно не копируется в Docker, бинарники на диске Space не переживают рестарт, сборка Windows-инсталлятора с wintun на CPU Space — плохой ToS и таймаут.

Почему не «один generic exe + пользователь вводит токен в GUI»: оператор явно хочет **скомпилированный под него файл после ввода кода на сайте**. Generic+sidecar допустим только как **аварийный fallback**, если передача артефакта Actions→Space застрянет; в целевом UX его нет.

Контракт сборки:

1. Пользователь шлёт **только token + platform** на публичный API origin (Space).
2. Origin считает SHA-256 токена, находит pending enrollment, **не** consume (consume — на `/enroll` при первом запуске приложения, как сейчас).
3. Origin создаёт job в Mongo (`installer_jobs`): `job_id`, `client_id`, platform, status, hash одноразового `download_secret`, TTL.
4. Origin триггерит workflow **только с `job_id`**. Сырой `enrollment_token` в `repository_dispatch` и в логах Actions **не** светить.
5. Runner забирает у origin по `X-Another-Proxy-Secret` пакет для ldflags (token, client_id, nodes JSON с реальным `control_plane` = URL воркера, не `:8787`).
6. `go build -trimpath -ldflags ... -o ... ./cmd/desktop` как в `another_admin/domain/builder.py`.
7. Кладёт рядом `wintun.dll` (amd64, лицензия Wintun — сохранить NOTICE). Для среза достаточно zip: `another.exe` + `wintun.dll`. Inno/NSIS «Next-Next-Finish» — сразу после того, как zip ставится и работает; не блокировать автоэнролл инсталлятором.
8. Runner **заливает артефакт обратно на origin** (`PUT /internal/v1/installer-jobs/{id}/artifact`). Origin держит файл коротко (например 2 часа) в каталоге вне git, отдаёт по одноразовому/короткоживущему секрету скачивания. Mongo GridFS на 15 МБ не использовать.
9. Страница портала поллит `GET /public/v1/installer-jobs/{id}` (без токена enroll, только `job_id` + download secret из шага redeem) и показывает «Скачать».

Секрет `GITHUB_TOKEN` / PAT с `actions:write` — в secrets Space, не в репозиторий. Workflow: `workflow_dispatch` + `repository_dispatch`, environment как у `another-edge-deploy.yml`. Fail-fast если секреты пустые.

### 3.2. Публичный портал vs админка

| URL | Кто | Что |
| --- | --- | --- |
| `/another/` | любой | витрина: поле кода, платформа, статус job, кнопка скачать. Ссылка «для оператора» на `/another/admin/` мелким текстом |
| `/another/admin/` | оператор | как сейчас, без редиректа с корня |
| `/another/public/v1/*` | браузер пользователя | redeem, status, download. Без админских подписей. Rate limit по IP |
| `/another/admin/v1/*` | админ-ключ | без изменений модели |
| `/another/internal/v1/*` | только воркер и **build runner** | существующий секрет сервиса |

Корень приложения в `create_app()` сейчас:

```python
return RedirectResponse(f"{request.scope.get('root_path', '')}/admin/")
```

Заменить на раздачу статики портала (`/`, `/index.html`). Админку оставить на `/admin`. `_needs_store` в `another/main.py` должен считать публичную статику такой же «лёгкой», как `/admin` без `/admin/v1`, иначе первый заход на витрину получит 503, пока Mongo не поднялся — витрина может открываться всегда; redeem без store — 503 с понятным текстом.

### 3.3. Кнопка Build в админке

Два разных действия, не смешивать:

- **Invite → пользователь на портале.** Pending stub уже есть. Портал собирает инсталлятор **для этого** `client_id` и **этого** токена. Reissue нет.
- **Build / Reissue на уже ENROLLED устройстве.** Как сейчас по смыслу: бан старого, новый token (замена телефона). Сборку после reissue можно сразу поставить в ту же очередь Actions. Предупреждение в UI: «старое устройство отвалится».

Текущий `build_installer`, который **всегда** зовёт `reissue_device`, для портала непригоден. Вынести `plan_installer` + enqueue job в отдельную функцию без revoke.

### 3.4. Поведение приложения при первом запуске

В `core/cmd/desktop/main.go` после `provisioning.Load()`:

1. `LoadOrCreateDeviceIdentity()`.
2. Если есть `bundle.EnrollmentToken` и ключ ещё не «привязан» локально (флаг в keystore / отсутствие успешного enroll): `POST {control_plane}/enroll` с `enrollment_token`, `public_key`, `public_key_mldsa65`. `control_plane` брать из embed nodes, иначе `ANOTHER_CONTROL_PLANE_URL`. Не ходить на `127.0.0.1:8787` в прод-сборке (уже есть fail-fast — оставить).
3. Ответ: сохранить `client_id`, `nodes` (host/control_plane с воркера), забыть token на диске (`ForgetToken`).
4. Сразу `ConnectUseCase` **без** `dest_host` (полный VPN), если не задан `ANOTHER_ALLOW_NOOP_TUN`.
5. Процесс живёт, пока VPN нужен. Минимальный UX среза: окно консоли или крошечный tray (Connect/Disconnect/Quit). Не ждать готовности Flutter.

Повторный запуск: token уже нет → только `/auth` + connect. Скопированный неактивированный exe после успешного enroll другого человека получит `403` на enroll — так и задумано.

Локальный HTTP `:47821` можно оставить для отладки; пользователю знать о нём не обязательно.

### 3.5. Платформы среза

Первый вертикальный срез: **Windows 10/11 amd64**. Linux zip — сразу, если дешево (тот же job, другой `GOOS`). Android/Flutter — не в этом плане (gomobile у оператора, как в ADR 0007).

---

## 4. Порядок работ для Opus (каждая фаза сама по себе катится на `main`)

Не делать «большой взрыв». После каждой фазы оператор должен мочь проверить руками.

### Фаза A — документы скоупа

- ADR 0004, provisioning.md, release-plan B.8: сайт самообслуживания **в скоупе**.
- DEPLOY.md: таблица URL — `/another/` это портал, не редирект.
- GETTING-STARTED: в конце абзац «лабораторный curl ≠ продукт»; продукт = этот документ.

### Фаза B — ядро само регистрируется и коннектится

Критерий: оператор собирает exe **локально** с ldflags (как печатает нынешний Build), запускает от администратора с `wintun.dll`, **без curl**. В админке ENROLLED + сессия (полный VPN) либо хотя бы AUTH_OK.

- HTTP-клиент enroll в `core` (переиспользовать challenge adapter / простой `net/http`).
- Не логировать token.
- Тесты: fake enroll server, повторный старт без второго enroll, 403 used token.
- Пока Actions нет — сборочная команда в README ядра достаточна для догфуда оператора.

### Фаза C — `/another/` не редиректит + форма

- Статика портала (тот же визуальный язык, что админка: тёмная, RU/EN не обязателен в срезе, лучше сразу ключи i18n как в админке).
- Поле кода, кнопка, состояния: idle / invalid / queued / building / ready / expired.
- Пока нет API — кнопка может показывать честную заглушку, но **корень уже не админка**.
- Тест: `GET /another/` 200 HTML, `GET /another/admin/` по-прежнему админка.

### Фаза D — публичный API + job в Mongo + Actions

- `POST /public/v1/redeem` `{ "token", "platform" }` → `{ job_id, download_secret, poll_url }`. Одинаковый ответ на несуществующий/просроченный token (анти-перебор), плюс rate limit.
- Коллекция `installer_jobs`, TTL индекс.
- Internal: выдача payload раннеру, приём артефакта, скачивание по secret.
- Workflow `another-installer-build.yml`: Windows или Ubuntu с `GOOS=windows GOARCH=amd64` + скачивание wintun в job.
- Секреты: тот же `ANOTHER_SERVICE_SECRET`, URL origin `https://nargan-projects.hf.space/another`, PAT/dispatch.
- Тесты origin без реального GitHub: fake runner.

Критерий: ввод живого invite-токена на сайте → через минуту zip качается → фаза B отрабатывает.

### Фаза E — «как приложение»

- Zip с `another.exe` + `wintun.dll` + короткий README (запуск от администратора один раз / манифест requireAdministrator).
- По возможности: Inno Setup, ярлык, автозапуск после установки.
- Трей или скрытие консоли. Disconnect по Quit — `kill switch` disarm как в существующем use-case.

### Фаза F — монитор глазами оператора

Почти бесплатно, если B+D сделаны. Проверить:

- Invite pending → после запуска ENROLLED.
- Сессия в «Active sessions» при поднятом VPN (полный, не dest_host).
- События `auth_ok`, не `dev-device`.
- Старый `edge_ban_invalidate_failed` / loopback: не регрессировать правки админки.
- Не жать Build на живом ENROLLED во время догфуда портала.

---

## 5. Чего не делать в этом срезе

- Компиляция Go внутри Docker Space / `ANOTHER_BUILD_ENABLED=1` на HF.
- Сайт, где **кто угодно** заказывает VPN без инвайта оператора.
- Логин пользователя (email/пароль). Идентичность = ключ устройства после enroll.
- Flutter как обязательный GUI этого среза.
- macOS/iOS.
- Класть enrollment_token в query string, в логи uvicorn, в `repository_dispatch` payload, в имя файла артефакта.
- GridFS / Mongo для бинарников.
- Менять протокол `/enroll`/`/auth` воркера «заодно».
- Считать успешным смоук с `dest_host=example.com` и российским IP браузера — это не VPN.

---

## 6. Как оператор прогоняет «сам на себе» после реализации

1. Админка: Invite, скопировать token (не client_id).
2. Выйти из админки / другое окно: открыть `/another/`, вставить token, Windows.
3. Скачать zip, закрыть лабораторный `another-core.exe` из GETTING-STARTED.
4. Поставить/запустить новый exe от администратора, другое VPN выключить.
5. IP-чек в браузере (не QUIC-only; часть сайтов за Cloudflare может врать — см. GETTING-STARTED часть 2).
6. Админка: то же устройство ENROLLED, сессия, не `dev-device`.

Если Actions ещё нет, а фаза B уже есть: оператор один раз собирает у себя с ldflags из вывода старой кнопки Build **на PENDING-инвайте без reissue** — это промежуточный догфуд, не продукт.

---

## 7. Файлы, которые почти наверняка изменятся

Ориентир, не догма:

- `another/control-plane-admin/another_admin/api/app.py` — корень, mount портала
- `another/control-plane-admin/another_admin/api/public_routes.py` — новый
- `another/control-plane-admin/another_admin/api/internal_routes.py` — job для runner
- `another/control-plane-admin/another_admin/api/admin_routes.py` — разделить reissue и compile
- `another/control-plane-admin/another_admin/domain/builder.py` — enqueue + не только «команда»
- `another/control-plane-admin/another_admin/adapters/async_mongo_store.py` — jobs
- `another/control-plane-admin/another_admin/api/static/` — портал рядом с админкой, разные mount
- `another/main.py` — `_needs_store`
- `another/core/cmd/desktop/main.go` + новый enroll-клиент в `internal/adapters/`
- `another/core/internal/adapters/provisioning/embed.go` — без смены контракта ldflags
- `.github/workflows/another-installer-build.yml` — новый
- `another/docs/adr/0004-invite-bound-tofu.md`, `provisioning.md`, `release-plan.md`, `DEPLOY.md`
- тесты: `tests/test_api.py`, `tests/test_builder.py`, Go-тесты enroll-on-start

Секреты Space/GitHub, которые понадобятся: URL origin, `ANOTHER_SERVICE_SECRET` (уже есть), токен для `repository_dispatch`, `CLOUDFLARE_*` не обязателен для этой фичи.

---

## 8. Риски, которые агент должен назвать в PR, а не замять

- HF Space должен **принять** большой PUT артефакта (таймаут прокси). Если нет — грузить в R2/GitHub Release (private) и отдать пользователю подписанный URL; origin тогда хранит только метаданные.
- `workers.dev` режется целиком (circumvention.md). Инсталлятор с зашитым `*.workers.dev` в РФ может не коннектиться. Это не чинится порталом; свой домен — отдельный трек.
- Два VPN сразу ломают маршруты. Написать в портале одной строкой.
- Wintun требует права администратора. Без этого снова `tun: using noop`.
- Очередь Actions на бесплатном плане — минуты. UI обязан сказать «собирается», а не висеть молча.

---

## Подпись

План составил **Cursor Grok 4.6** 27 августа 2026. Реализация — в той же модели, той же дате: портал, public API, очередь Actions, автоэнролл ядра.
