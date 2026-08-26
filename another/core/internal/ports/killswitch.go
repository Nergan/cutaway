package ports

import "context"

// DestinationPermitter — опциональное расширение KillSwitchPort: список
// IP/хостов, которые можно обходить туннель (входы VPN и control-plane).
// Вызывается после пробника, до Arm.
type DestinationPermitter interface {
	SetPermitDestinations(addrs []string)
}

// KillSwitchPort — driven-порт: при обрыве туннеля трафик не должен
// утекать в открытую сеть. Служебные адреса (узлы из Permit) остаются
// достижимы для reconnect.
//
//   - Windows: маршруты 0.0.0.0/1 + 128.0.0.0/1 через Wintun; при drop —
//     blackhole default. WFP — усиление, если есть права.
//   - Android: VpnService.Builder (setBlocking, без allowBypass) на
//     Kotlin-стороне; Go-адаптер фиксирует armed-состояние.
//   - Linux: nftables таблица inet another.
//   - iOS/macOS: вне релиза, заглушки.
type KillSwitchPort interface {
	// Arm включает блокировку "мимо туннеля". После фазы 2 ошибка Arm —
	// фатальна для Connect (не подключаемся без гарантии).
	Arm(ctx context.Context) error

	// Disarm снимает блокировку. Только по явному отключению пользователем.
	Disarm(ctx context.Context) error

	// OnTunnelDropped — обрыв не по команде пользователя. Усиливает
	// блокировку до восстановления.
	OnTunnelDropped(ctx context.Context) error
}
