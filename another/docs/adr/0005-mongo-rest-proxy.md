# ADR 0005: Self-hosted REST-прокси вместо Atlas Data API

## Статус
Принято (аудит 2026-08-25).

## Контекст
`edge/src/adapters/mongo_atlas_user_repository.ts` ходит в MongoDB Atlas
Data API. App Services / Data API достигли EOL **30 сентября 2025**.
Worker не умеет Mongo wire protocol по TCP нормальным драйвером.
Оператор выбрал self-hosted REST-прокси из вариантов (прокси / D1 /
убрать Worker с hot path).

## Решение
- Источник истины — по-прежнему Atlas по `MONGO_URI`.
- Тонкий HTTPS API на HF Space (резерв Render), нативный PyMongo Async.
- Worker вызывает только этот API (сервисный секрет, не пользовательский).
- Админ-API живёт там же (другие пути, другая аутентификация).
- Не берём чужой «drop-in Data API» (Delbridge и т.п.) как новую зависимость
  на критическом пути — контракт узкий (`findClient`, `enroll`, `ban`,
  `quota`), пишем сами.

Не переносим hot-path авторизации целиком на Render: теряется смысл
гео-входа Cloudflare на вайтлистах.

## Последствия
Пока прокси не написан, `/enroll` и `/auth` в реальном деплое **не ходят**
в базу. Это блокер фазы 1 ([release-plan.md](../release-plan.md)).
`MONGO_DATA_API_*` из `.env` выводятся из употребления.
