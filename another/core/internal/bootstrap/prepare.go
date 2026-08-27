package bootstrap

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/another-vpn/another/core/internal/adapters/provisioning"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

type EnrollClient interface {
	Enroll(ctx context.Context, controlPlane, token, pubHex, pubMLDSAHex string) (string, []domain.NodeDescriptor, error)
}

type PreparedSession struct {
	ClientID    string
	Policy      *domain.FailoverPolicy
	AutoConnect bool
}

func IsLoopbackURL(raw string) bool {
	u := strings.ToLower(raw)
	return strings.Contains(u, "127.0.0.1") || strings.Contains(u, "localhost") || strings.Contains(u, "[::1]")
}

func ControlPlaneFrom(bundle provisioning.Bundle, fallback string) string {
	for _, n := range bundle.Entrypoints {
		if strings.TrimSpace(n.ControlPlane) != "" {
			return n.ControlPlane
		}
	}
	return fallback
}

// PrepareSession: receipt → уже enrolled; иначе token из embed → /enroll.
func PrepareSession(
	ctx context.Context,
	logger *slog.Logger,
	ks ports.KeyStorePort,
	enroller EnrollClient,
	keystoreDir string,
	bundle provisioning.Bundle,
	fallbackControlPlane string,
) (PreparedSession, error) {
	if logger == nil {
		logger = slog.Default()
	}
	rec, ok, err := provisioning.LoadReceipt(keystoreDir)
	if err != nil {
		return PreparedSession{}, fmt.Errorf("bootstrap: load receipt: %w", err)
	}
	if ok {
		return PreparedSession{
			ClientID:    rec.ClientID,
			Policy:      domain.NewFailoverPolicy(rec.Nodes),
			AutoConnect: len(rec.Nodes) > 0 && rec.ClientID != "",
		}, nil
	}
	token := strings.TrimSpace(bundle.EnrollmentToken)
	if token == "" {
		return PreparedSession{ClientID: bundle.ClientID}, nil
	}
	cp := ControlPlaneFrom(bundle, fallbackControlPlane)
	if IsLoopbackURL(cp) {
		return PreparedSession{}, fmt.Errorf("bootstrap: control_plane is loopback, refusing auto-enroll")
	}
	identity, err := ks.LoadOrCreateDeviceIdentity()
	if err != nil {
		return PreparedSession{}, fmt.Errorf("bootstrap: identity: %w", err)
	}
	clientID, nodes, err := enroller.Enroll(ctx, cp, token, identity.PublicKeyHex(), identity.MLDSAPublicKeyHex())
	if err != nil {
		return PreparedSession{}, err
	}
	if len(nodes) == 0 {
		nodes = bundle.Entrypoints
	}
	if err := provisioning.SaveReceipt(keystoreDir, provisioning.Receipt{ClientID: clientID, Nodes: nodes}); err != nil {
		return PreparedSession{}, fmt.Errorf("bootstrap: save receipt: %w", err)
	}
	logger.Info("enrolled", "client_id", clientID)
	return PreparedSession{
		ClientID:    clientID,
		Policy:      domain.NewFailoverPolicy(nodes),
		AutoConnect: true,
	}, nil
}
