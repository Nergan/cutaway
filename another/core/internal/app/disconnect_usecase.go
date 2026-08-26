package app

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// DisconnectUseCase закрывает активный туннель и снимает kill switch.
// Snap switch снимается ТОЛЬКО здесь — по явному действию пользователя, а не
// при любом обрыве соединения (см. KillSwitchPort.OnTunnelDropped против
// Disarm в §5.4 спецификации).
type DisconnectUseCase struct {
	Session    *domain.TunnelSession
	Tunnel     ports.TunnelPort
	KillSwitch ports.KillSwitchPort
	Logger     *slog.Logger
}

func NewDisconnectUseCase(session *domain.TunnelSession, tunnelPort ports.TunnelPort, killSwitch ports.KillSwitchPort, logger *slog.Logger) *DisconnectUseCase {
	if logger == nil {
		logger = slog.Default()
	}
	return &DisconnectUseCase{Session: session, Tunnel: tunnelPort, KillSwitch: killSwitch, Logger: logger}
}

func (uc *DisconnectUseCase) Execute(ctx context.Context) error {
	if err := uc.Tunnel.Unbind(ctx); err != nil {
		uc.Logger.Warn("tun unbind failed", "error", err)
	}
	if err := uc.KillSwitch.Disarm(ctx); err != nil {
		uc.Logger.Warn("killswitch disarm failed", "error", err)
	}
	uc.Session.SetDisconnected()
	uc.Logger.Info("disconnected")
	return nil
}

// ErrNotConnected — попытка выполнить операцию, требующую активного
// соединения, когда его нет.
var ErrNotConnected = fmt.Errorf("app: no active connection")
