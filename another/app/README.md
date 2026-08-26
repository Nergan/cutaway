# `app/` — Flutter GUI

Гексагональная архитектура: `domain/` (entities, ports) → `application/`
(use-cases) → `infrastructure/` (HTTP/MethodChannel/secure storage адаптеры)
→ `presentation/` (AppState + screens/widgets). UI **только на английском**
языке (осознанное решение — экономия ресурсов на необязательный функционал,
приоритет: скорость, анонимизация трафика, кроссплатформенность).

## Честная оговорка про верификацию

**В этой среде разработки нет Flutter SDK и нет доступа к pub.dev/`storage.googleapis.com`**
(проверено — оба хоста отдают `403 host_not_allowed` в используемом сетевом
окружении). Это значит: код в `lib/` и `test/` написан и вычитан вручную
(включая грубую автоматическую проверку баланса скобок по всем файлам и
валидацию `pubspec.yaml` как YAML), но **не прогонялся через `flutter analyze`,
`dart compile` или `flutter test`**. Тот же класс ограничения, что для Xcode
(Part 1, iOS) и реального `mongod` (Part 3) — честно документируется, а не
маскируется.

Что нужно сделать в реальном Flutter-окружении перед первым запуском:

```bash
flutter --version                      # 3.22+
flutter create --platforms=android,ios,windows,macos,linux --org com.another .
# ^ это перезапишет pubspec.yaml — после генерации native-папок верните
#   наш pubspec.yaml обратно и добавьте недостающие platform-папки в git
flutter pub get
flutter analyze                        # первая реальная проверка типов
flutter test                           # test/domain/*.dart — pure-Dart тесты
```

## Что реально сделано (архитектурно и логически завершено)

- **Domain**: `NodeDescriptor`/`Profile`/`SessionSnapshot`/`VpnSessionState` —
  зеркалят wire-формат, уже согласованный между Go (`core/`) и TS (`edge/`);
  JSON-теги snake_case совпадают буква-в-букву на всех трёх границах.
- **Application**: `EnrollUseCase`, `ConnectUseCase`, `DisconnectUseCase`,
  `SwitchNodeUseCase`, `LoadProfileUseCase` — соответствуют §6.1
  спецификации и Go-эквивалентам в `core/internal/app/`.
- **Infrastructure**:
  - `HttpCoreAdapter` — десктоп, реальный HTTP-клиент к локальному control
    API `core/cmd/desktop/main.go` (эндпоинты `/identity`, `/connect`,
    `/switch`, `/disconnect`, `/status` — все подтверждены существующими на
    Go-стороне, см. Part 1).
  - `PlatformChannelCoreAdapter` — мобильные платформы, см. правку ниже.
  - `ConfigRepositoryHttpAdapter` — прямой HTTP к `edge/enroll`
    (подтверждено согласование полей с `edge/src/handlers/enroll.ts`).
  - `SecureProfileStorageAdapter` — обёртка над `flutter_secure_storage`.
- **Presentation**: `AppState` (единственный `ChangeNotifier`) + 4 экрана
  (onboarding/home/node picker/settings) + 2 виджета.
- **19 pure-Dart unit-тестов** (`test/domain/`) — JSON round-trip, порядок
  переприоритезации узлов, разбор инвайт-ссылки. Написаны в том же стиле,
  что тесты Go/TS/Python в предыдущих частях (проверяют логику без
  реального Flutter-виджет-дерева, значит потенциально прогоняемы и
  через обычный `dart test`, если `flutter_test` заменить на `test` —
  не сделано специально, чтобы остаться в стандартном Flutter-тулчейне).

## Правка относительно архитектурной спецификации: мобильный мост

§5.2/§6.2 `docs/architecture.md` называли мобильный мост "dart:ffi".
`gomobile bind` генерирует Java/Kotlin-классы. Клей фазы 3:
`app/native/android/` (`AnotherCorePlugin` + `AnotherVpnService`).
Инструкция сборки `.aar` — `app/native/android/README.md`. iOS вне релиза.

## Архитектурная правка, найденная при проектировании онбординга (затронула `core/`)

При проектировании `EnrollUseCase` обнаружился порядок-зависимый баг в
`core/`: устройство должно сгенерировать публичный ключ и отправить его в
`/enroll` ДО того, как узнает свой серверный `client_id` — а
`KeyStorePort.LoadOrCreateDeviceIdentity` в Go изначально был
параметризован именно `client_id`. Исправлено в `core/` (см.
`core/README.md`, раздел "Правка при интеграции с Flutter") — идентичность
устройства больше не индексируется по `client_id`. Заодно добавлены `GET
/identity`, `POST /switch` в `core/cmd/desktop/main.go` и
`GetPublicKey`/`SwitchNode` в `core/cmd/mobilelib/binding.go` — без них
GUI не мог бы реализовать ни онбординг, ни ручное переключение узла.

## Чего не хватает для полностью рабочего приложения (TODO v2)

| Что | Почему не в этой сессии |
|---|---|
| Нативные platform-папки (`android/`, `ios/`, `windows/`, `macos/`, `linux/`) | Генерируются `flutter create`, не воспроизводимы вручную корректно — не Flutter SDK в этой среде. |
| Нативный код-мост MethodChannel на Kotlin | Шаблон в `app/native/android/`. `.aar` — `gomobile bind` у оператора. |
| Нативный мост iOS | Вне релиза (ADR 0007). |
| Реальный перехват трафика на устройстве | Зависит от `core/internal/adapters/tun/*` — задокументированные заглушки (Part 1). |
| `flutter analyze`/`flutter test` прогон | Недоступный Flutter SDK/pub.dev в этой среде, см. выше. |

## Локальный запуск (после `flutter create` в реальном окружении)

```bash
# Десктоп, вместе с уже поднятым Core (см. core/README.md):
flutter run -d macos   # или windows/linux
```
