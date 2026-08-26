// Package tun содержит реализации ports.TunnelPort.
package tun

import (
	"context"
	"log/slog"

	"github.com/another-vpn/another/core/internal/ports"
)

// NoopTun — рабочая (не заглушка) dev/test-реализация: не перехватывает
// реальный системный трафик, но полностью прогоняет жизненный цикл
// Bind/Unbind, что достаточно для сквозного тестирования
// Connect/Disconnect/failover без необходимости root-прав или реального
// сетевого стека ОС. Реальные платформенные адаптеры — TODO v2,
// см. platform_stub.go.
type NoopTun struct {
	Logger  *slog.Logger
	current ports.Tunnel
	dialer  ports.StreamDialer
}

func NewNoopTun(logger *slog.Logger) *NoopTun {
	if logger == nil {
		logger = slog.Default()
	}
	return &NoopTun{Logger: logger}
}

func (n *NoopTun) Bind(ctx context.Context, tunnel ports.Tunnel) error {
	n.Logger.Info("tun: bind (noop — системный трафик не перехватывается)")
	n.current = tunnel
	return nil
}

func (n *NoopTun) BindDialer(ctx context.Context, dial ports.StreamDialer) error {
	n.Logger.Info("tun: bind dialer (noop — пакетный перехват выключен)")
	n.dialer = dial
	return nil
}

func (n *NoopTun) Unbind(ctx context.Context) error {
	n.Logger.Info("tun: unbind (noop)")
	n.dialer = nil
	if n.current != nil {
		err := n.current.Close()
		n.current = nil
		return err
	}
	return nil
}
