package ports

import "context"

// PacketDevice — сырой L3 TUN: IP-пакеты без ethernet-заголовка.
type PacketDevice interface {
	ReadPacket(buf []byte) (int, error)
	WritePacket(pkt []byte) error
	Close() error
	Name() string
}

// StreamDialer открывает один VLESS-поток до dest (из заголовка пакета).
// network: "tcp" или "udp".
type StreamDialer func(ctx context.Context, network, host string, port uint16) (Tunnel, error)

// StackBinder — полноценный VPN-режим: TUN + userspace NAT (tun2vless).
// NoopTun тоже реализует его (без перехвата), чтобы тесты Connect в VPN-
// режиме не требовали root.
type StackBinder interface {
	BindDialer(ctx context.Context, dial StreamDialer) error
}

// TunnelPort — driven-порт для работы с сетевым TUN-интерфейсом ОС.
// Bind связывает уже установленный Tunnel с системным стеком (режим
// одного назначения, для тестов и ручного прокси). Полноценный VPN —
// BindDialer на StackBinder: пакеты из ОС разбираются, на каждый поток
// открывается свой Dial.
//
// Платформы релиза (ADR 0007): Windows 10/11 (Wintun), Linux (/dev/net/tun),
// Android (fd от VpnService). macOS/iOS — заглушки вне релиза.
type TunnelPort interface {
	Bind(ctx context.Context, tunnel Tunnel) error
	Unbind(ctx context.Context) error
}
