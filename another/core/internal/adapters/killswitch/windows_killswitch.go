//go:build windows

package killswitch

import (
	"context"
	"fmt"
	"os/exec"
	"sync"
)

// WindowsKillSwitch — маршрутный kill switch: /1 через TUN уже ставит
// tun.configureWindowsIface. Здесь: permit-хосты /32 через исходный
// шлюз (чтобы вход был достижим) и blackhole при drop.
type WindowsKillSwitch struct {
	mu      sync.Mutex
	permit  []string
	armed   bool
	dropped bool
}

func NewWindowsKillSwitch() *WindowsKillSwitch { return &WindowsKillSwitch{} }

func (w *WindowsKillSwitch) SetPermitDestinations(addrs []string) {
	w.mu.Lock()
	w.permit = append([]string(nil), addrs...)
	w.mu.Unlock()
}

func (w *WindowsKillSwitch) Arm(ctx context.Context) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	for _, ip := range w.permit {
		if ip == "" {
			continue
		}
		// /32 на permit, чтобы handshake входа не ушёл в TUN до сессии.
		_ = exec.CommandContext(ctx, "route", "add", ip, "mask", "255.255.255.255", "0.0.0.0", "metric", "1").Run()
	}
	w.armed = true
	w.dropped = false
	return nil
}

func (w *WindowsKillSwitch) Disarm(ctx context.Context) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	_ = exec.CommandContext(ctx, "route", "delete", "0.0.0.0", "mask", "0.0.0.0", "127.0.0.1").Run()
	for _, ip := range w.permit {
		_ = exec.CommandContext(ctx, "route", "delete", ip, "mask", "255.255.255.255").Run()
	}
	w.armed = false
	w.dropped = false
	return nil
}

func (w *WindowsKillSwitch) OnTunnelDropped(ctx context.Context) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	out, err := exec.CommandContext(ctx, "route", "add", "0.0.0.0", "mask", "0.0.0.0", "127.0.0.1", "metric", "1").CombinedOutput()
	if err != nil {
		return fmt.Errorf("killswitch: blackhole: %w (%s)", err, out)
	}
	w.dropped = true
	return nil
}
