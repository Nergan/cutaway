# Another: пауза разработки

**Дата паузы:** 2026-08-27.  
**Последний коммит кода:** `8e8d319` (`another: портал invite→zip, автоэнролл ядра, админка только по кнопке.`).  
Разработку не продолжать, пока оператор явно не снимет паузу.

Остальная документация (`docs/*`, README, DEPLOY, GETTING-STARTED) **не в git** — только в рабочей копии. Этот файл — единственная точка входа.

---

## Почему остановились

Hugging Face Space `Nargan/projects` в `PAUSED` с `errorMessage: Flagged as abusive`. Restart / Rebuild / factory reboot **не поднимают** контейнер. Это не падение uvicorn и не «прокси на ПК».

Origin на Space **не гоняет VPN**. Трафик туннеля — Cloudflare Worker. В логах до `Shutting down` были `POST /another/admin/v1/command 200` (открытая админка, тогда поллинг раз в 10 с) и `GET /another/internal/v1/ping-targets` (воркер). Клиентский VPN до рабочего полного туннеля **не довели**.

Снятый флаг abusive — только через HF (страница Space / https://huggingface.co/support). Пока Space мёртв, портал и origin API недоступны; воркер может жить отдельно.

---

## Что уже сделано в коде (`main`)

- Публичный портал: `GET /another/` — витрина (код → zip), не редирект в админку. Админка — `/another/admin/`.
- `POST /public/v1/redeem`, статус и скачивание zip. Токен enroll **не** consume на redeem. Антиперебор: одна фраза `invalid or expired invite`.
- Сборка zip в GitHub Actions (`.github/workflows/another-installer-build.yml`): exe + `wintun.dll` + README. В dispatch только `job_id`.
- Ядро: `POST /enroll`, `enrolled.json`, автоконнект полного VPN (пустой `dest_host`). Лаборатория: `ANOTHER_SKIP_AUTO_START=1`.
- Админка: **нет автополлинга**. Unlock грузит данные один раз; дальше кнопки «Обновить» и «Прогнать детектор».
- TOFU без ключа в exe (ADR 0004). Кнопка «Собрать» в админке по-прежнему **reissue**.

## Что не сделано / не проверено в проде

- Секреты портала на Space (`GITHUB_REPO=Nergan/cutaway`, `GITHUB_DISPATCH_TOKEN`) и в GitHub Actions (`ANOTHER_ORIGIN_URL`, тот же `ANOTHER_SERVICE_SECRET`) — могли быть не выставлены; без них redeem → 503.
- Цикл Invite → портал → zip → exe от админа на живом Space **не прогнан** (Space уже стоял на паузе).
- Полный VPN Windows (права администратора, `wintun.dll` рядом, без второго VPN) — не подтверждён.
- Flutter GUI нет. Inno Setup нет. Свой домен вместо `*.workers.dev` нет (`workers.dev` режется в РФ).
- Большой PUT zip на HF может отвалиться по таймауту прокси.

Лабораторный curl (GETTING-STARTED в рабочей копии) раньше доходил до `AUTH_OK` / `connected` на смоуке с `dest_host` — это не полный VPN.

---

## Как возобновить

1. HF снимает `Flagged as abusive`, Space Running.
2. Секреты — по локальному `DEPLOY.md` (не генерировать новый `ANOTHER_SERVICE_SECRET`, если старый уже в Cloudflare). PAT для dispatch: Contents Read and write, не `actions:write`.
3. Не возвращать автополлинг админки.
4. Для нового человека — Invite + портал, не Build на живом ENROLLED.
5. Документация: если файла нет в клоне — он только на машине, где была пауза, либо восстановить из этой копии.

Код трогать не нужно, пока нет живого origin.
