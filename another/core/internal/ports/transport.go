package ports

import (
	"context"
	"io"

	"github.com/another-vpn/another/core/internal/domain"
)

// Tunnel — открытое дуплексное соединение до точки входа после успешного
// протокольного рукопожатия (VLESS-заголовок принят и подтверждён).
// Именно через него TunnelPort читает/пишет пакеты, полученные из
// TUN-интерфейса ОС.
type Tunnel interface {
	io.ReadWriteCloser
}

// OutboundTransportPort — driven-порт: как ядро устанавливает соединение
// до конкретного узла (Cloudflare Worker, Render, VPS с Reality...).
// Адаптеры: vless_ws.go (реализован), vless_grpc.go / vless_reality.go
// (заглушки с TODO — см. комментарии в файлах), echo_transport.go
// (рабочая dev/test-петля).
type OutboundTransportPort interface {
	// Dial устанавливает транспортное соединение и проводит VLESS-рукопожатие
	// до целевого хоста destHost:destPort (т.е. до реального адреса в
	// интернете, к которому клиент туннелирует трафик — не путать с node.Host,
	// который является адресом точки входа).
	Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (Tunnel, error)
}
