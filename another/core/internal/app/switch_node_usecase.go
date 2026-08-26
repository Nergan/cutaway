package app

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// SwitchNodeUseCase переключает активное соединение на конкретный узел,
// выбранный пользователем вручную (например, из UI — §6.1 спецификации,
// use-case SwitchNodeUseCase). В отличие от ConnectUseCase, kill switch не
// снимается между отключением от старого узла и подключением к новому —
// иначе в этом окне трафик мог бы утечь мимо туннеля.
type SwitchNodeUseCase struct {
	Session   *domain.TunnelSession
	KeyStore  ports.KeyStorePort
	Auth      ports.AuthPort
	Transport ports.OutboundTransportPort
	Tunnel    ports.TunnelPort
	Logger    *slog.Logger

	ClientID string
}

func NewSwitchNodeUseCase(
	session *domain.TunnelSession,
	keyStore ports.KeyStorePort,
	auth ports.AuthPort,
	transport ports.OutboundTransportPort,
	tunnelPort ports.TunnelPort,
	clientID string,
	logger *slog.Logger,
) *SwitchNodeUseCase {
	if logger == nil {
		logger = slog.Default()
	}
	return &SwitchNodeUseCase{
		Session: session, KeyStore: keyStore, Auth: auth,
		Transport: transport, Tunnel: tunnelPort, ClientID: clientID, Logger: logger,
	}
}

func (uc *SwitchNodeUseCase) Execute(ctx context.Context, target domain.NodeDescriptor, destHost string, destPort uint16) error {
	snap := uc.Session.Snapshot()
	if snap.State != domain.StateConnected {
		return ErrNotConnected
	}

	// Закрываем старый туннель, но НЕ трогаем kill switch — он остаётся
	// armed на протяжении всего переключения.
	if err := uc.Tunnel.Unbind(ctx); err != nil {
		uc.Logger.Warn("tun unbind during switch failed", "error", err)
	}
	uc.Session.SetReconnecting()

	identity, err := uc.KeyStore.LoadOrCreateDeviceIdentity()
	if err != nil {
		uc.Session.SetFailed(err)
		return fmt.Errorf("app: load device identity: %w", err)
	}

	creds, err := uc.Auth.ChallengeResponse(ctx, target, uc.ClientID, identity)
	if err != nil {
		uc.Session.SetFailed(err)
		return fmt.Errorf("app: switch node auth: %w", err)
	}

	tunnel, err := uc.Transport.Dial(ctx, target, creds, destHost, destPort)
	if err != nil {
		uc.Session.SetFailed(err)
		return fmt.Errorf("app: switch node dial: %w", err)
	}

	if err := uc.Tunnel.Bind(ctx, tunnel); err != nil {
		_ = tunnel.Close()
		uc.Session.SetFailed(err)
		return fmt.Errorf("app: switch node bind: %w", err)
	}

	targetCopy := target
	uc.Session.SetConnected(&targetCopy)
	uc.Logger.Info("switched node", "node", target.Name)
	return nil
}
