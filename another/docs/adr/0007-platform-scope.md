# ADR 0007: Платформенный скоуп релиза

## Статус
Принято (аудит 2026-08-25).

## Контекст
Спецификация v2.0 обещала Android, iOS, Windows, macOS, Linux. Оператор
хочет максимум платформ, но явно: Windows 7/8/10/11 (XP «как повезёт»),
много Linux, Android; macOS/iOS можно отложить. Кроссплатформенность —
один из двух главных принципов.

Ограничения toolchain (не желание):

- Go ≥ 1.21: Windows 10+ / Server 2016+. Go 1.20 — последний с Win 7/8.
- Flutter 3.19+ не поддерживает Windows 7/8; GUI на 7/8 = не Flutter.
- Windows XP: современный Go/TLS/Flutter не собираются во что-то, чему
  можно доверять. Не обещать.
- iOS TUN требует Apple developer + Xcode; оператор готов забить.

## Решение

| Платформа | Релиз | Как |
|---|---|---|
| Windows 10/11 (amd64, arm64 по возможности) | Да | Go current + Flutter GUI + Wintun + WFP |
| Linux (x64/arm64, широкие дистрибутивы) | Да | TUN `/dev/net/tun` + nftables; GUI Flutter |
| Android | Да | gomobile + VpnService; Kotlin/Swift только клей MethodChannel |
| Windows 7/8 | Best-effort, отдельный контур | Заморозка Go 1.20, без Flutter, минимальный CLI/tray если получится |
| Windows XP | Нет | Не планировать |
| macOS, iOS | Вне релиза | Код-заглушки можно не вычищать, не развивать |

## Последствия
Кросс-компиляция `darwin`/`ios` в CI не блокер. Не писать «пять платформ
готовы». Скорость и TUN на трёх основных ОС важнее пятой платформы.
