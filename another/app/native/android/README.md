# Android-клей (фаза 3)

Kotlin **только как мост**: MethodChannel `another.core/control` → gomobile
`Mobilelib.*` + `VpnService`. Приложение не пишется на Kotlin.

iOS в релизе нет (ADR 0007). Сборку `.aar` агент не делает — нет Android SDK.

## Что сделать у оператора

1. В корне `app/`:

```bash
flutter create --platforms=android --org com.another .
# вернуть наш pubspec.yaml, если create его перезаписал
```

2. Скопировать:

- `app/native/android/src/main/kotlin/com/another/vpn/AnotherCorePlugin.kt`
- `app/native/android/src/main/kotlin/com/another/vpn/AnotherVpnService.kt`

в `app/android/app/src/main/kotlin/com/another/vpn/`.

3. Зарегистрировать плагин в `MainActivity` (после `flutter create`):

```kotlin
flutterEngine.plugins.add(AnotherCorePlugin())
```

4. В `AndroidManifest.xml` внутри `<application>`:

```xml
<service
    android:name=".AnotherVpnService"
    android:exported="false"
    android:foregroundServiceType="connectedDevice"
    android:permission="android.permission.BIND_VPN_SERVICE">
    <intent-filter>
        <action android:name="android.net.VpnService" />
    </intent-filter>
</service>
```

и permission `FOREGROUND_SERVICE` / `FOREGROUND_SERVICE_CONNECTED_DEVICE` по уровню SDK.

5. Собрать AAR из `core/`:

```bash
cd core
go install golang.org/x/mobile/cmd/gomobile@latest
gomobile init
# Windows: GOOS/GOARCH сбросить, иначе «not a valid Win32 application»
set GOOS=
set GOARCH=
gomobile bind -target=android -androidapi 24 -o ../app/android/app/libs/mobilelib.aar ./cmd/mobilelib
```

Подключить `mobilelib.aar` в `app/android/app/build.gradle` (`implementation files('libs/mobilelib.aar')`).
Пакет gomobile обычно называется `mobilelib` — импорт в Kotlin: `import mobilelib.Mobilelib`.

6. Порядок нативного connect (уже в `AnotherVpnService`):

`VpnService.establish()` → `SetTunFd(fd)` → `NotifyKillSwitchArmed()` → `Init` → `Connect("", 0)` (VPN, не один dest).

`wintun.dll` к Android не относится. Живой прогон VpnService — только на устройстве/эмуляторе оператора.
