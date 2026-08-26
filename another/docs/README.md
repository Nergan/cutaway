# Документация проекта Another

**Another** (англ. «ещё один» / «другой») — приватный VPN для закрытого круга.
Не публичный продукт: оператор выдаёт доступ конкретным людям.

Документы в `docs/` (кроме `docs/private/`) — часть репозитория и **источник
истины** для следующего агента или человека. Если код и документ расходятся —
сначала смотрите ADR и `implementation-plan.md`, затем код; расхождение нужно
либо исправить, либо явно зафиксировать.

## С чего начать

| Хотите понять… | Читайте |
|---|---|
| Что это за проект и какие у него принципы | [principles.md](principles.md) |
| Что уже сделано vs что задумано | [implementation-plan.md](implementation-plan.md), затем [release-plan.md](release-plan.md) |
| Как устроена система целиком | [architecture.md](architecture.md) |
| Какая инфраструктура реально есть | [infrastructure.md](infrastructure.md) |
| Как устроена аутентификация (админ и клиент) | [auth-spec.md](auth-spec.md) |
| Как выдаётся доступ устройствам | [provisioning.md](provisioning.md) |
| Будет ли VPN работать в РФ / КНР / при вайтлистах | [circumvention.md](circumvention.md) |
| Монитор, логи, алерты | [observability.md](observability.md) |
| Почему принято конкретное решение | [adr/](adr/) |

## Карта документов

```
docs/
├── README.md                 ← вы здесь
├── principles.md             принципы, имя, non-goals
├── architecture.md           техспецификация (живёт вместе с кодом)
├── implementation-plan.md    статус реализации по частям
├── release-plan.md           план доведения до рабочего состояния
├── infrastructure.md         доступные узлы и как их складывать
├── auth-spec.md              PQ-аутентификация админа и клиента (корректная)
├── provisioning.md           TOFU + invite, не ключ в бинарнике
├── circumvention.md          ТСПУ / вайтлисты / GFW / что брать из экосистемы
├── observability.md          монитор, компактные логи, оповещения
├── adr/                      architecture decision records
└── private/                  локальные заметки оператора (в .gitignore)
```

## Правило про `.gitignore`

Архитектурная документация **не** игнорируется: без неё агент не восстановит
замысел. В git не попадают секреты, ключи, сборки и `docs/private/` —
см. корневой `.gitignore` и § «Секреты» в [infrastructure.md](infrastructure.md).

## Язык

Документация и комментарии в коде — на русском. UI клиента — английский.
