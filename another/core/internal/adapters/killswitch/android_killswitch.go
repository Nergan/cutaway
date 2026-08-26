//go:build android

package killswitch

import (
	"context"
	"log/slog"
	"sync"
)

// AndroidKillSwitch — блокировка делает VpnService (setBlocking, без
// allowBypass). Go только помнит armed, чтобы Connect не шёл дальше без
// подтверждения нативного слоя (см. cmd/mobilelib.NotifyKillSwitchArmed).
type AndroidKillSwitch struct {
	Logger   *slog.Logger
	mu       sync.Mutex
	permit   []string
	nativeOK bool
	armed    bool
}

func NewAndroidKillSwitch(logger *slog.Logger) *AndroidKillSwitch {
	if logger == nil {
		logger = slog.Default()
	}
	return &AndroidKillSwitch{Logger: logger}
}

func (a *AndroidKillSwitch) SetPermitDestinations(addrs []string) {
	a.mu.Lock()
	a.permit = append([]string(nil), addrs...)
	a.mu.Unlock()
}

// ConfirmNative сообщает, что VpnService.establish() уже создал blocking TUN.
func (a *AndroidKillSwitch) ConfirmNative() {
	a.mu.Lock()
	a.nativeOK = true
	a.mu.Unlock()
}

func (a *AndroidKillSwitch) Arm(ctx context.Context) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if !a.nativeOK {
		a.Logger.Warn("killswitch: VpnService ещё не confirm — Arm как no-op с предупреждением")
	}
	a.armed = true
	return nil
}

func (a *AndroidKillSwitch) Disarm(ctx context.Context) error {
	a.mu.Lock()
	a.armed = false
	a.mu.Unlock()
	return nil
}

func (a *AndroidKillSwitch) OnTunnelDropped(ctx context.Context) error {
	a.Logger.Warn("killswitch: tunnel dropped; VpnService должен держать blocking=true")
	return nil
}
