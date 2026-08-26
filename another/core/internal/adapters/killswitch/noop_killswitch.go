// Package killswitch содержит реализации ports.KillSwitchPort.
package killswitch

import (
	"context"
	"log/slog"
)

// NoopKillSwitch — минимальная рабочая реализация: только логирует
// переходы состояний, ничего не блокирует на уровне ОС. Это default v1,
// достаточный для тестирования логики ConnectUseCase/failover, но НЕ
// обеспечивающий реальной защиты от утечки трафика — см. platform_stub.go
// про то, что нужно реализовать для каждой ОС в v2.
type NoopKillSwitch struct {
	Logger *slog.Logger
}

func NewNoopKillSwitch(logger *slog.Logger) *NoopKillSwitch {
	if logger == nil {
		logger = slog.Default()
	}
	return &NoopKillSwitch{Logger: logger}
}

func (n *NoopKillSwitch) Arm(ctx context.Context) error {
	n.Logger.Info("killswitch: ARM (noop — реальная блокировка трафика не активна)")
	return nil
}

func (n *NoopKillSwitch) Disarm(ctx context.Context) error {
	n.Logger.Info("killswitch: DISARM (noop)")
	return nil
}

func (n *NoopKillSwitch) OnTunnelDropped(ctx context.Context) error {
	n.Logger.Warn("killswitch: tunnel dropped, would block traffic (noop — see platform_stub.go)")
	return nil
}
