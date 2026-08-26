package tun

import (
	"context"
	"fmt"
	"log/slog"
	"sync"

	"github.com/another-vpn/another/core/internal/adapters/netstack"
	"github.com/another-vpn/another/core/internal/ports"
)

// StackTun — общий Bind/BindDialer поверх PacketDevice. Платформенные
// адаптеры только открывают устройство и поднимают адрес/маршруты.
type StackTun struct {
	Device ports.PacketDevice
	Logger *slog.Logger

	mu     sync.Mutex
	engine *netstack.Engine
	cancel context.CancelFunc
	single ports.Tunnel
}

func NewStackTun(dev ports.PacketDevice, logger *slog.Logger) *StackTun {
	if logger == nil {
		logger = slog.Default()
	}
	return &StackTun{Device: dev, Logger: logger}
}

func (s *StackTun) Bind(ctx context.Context, tunnel ports.Tunnel) error {
	// Режим одного потока: NAT всё равно поднимаем, но dialer всегда
	// возвращает этот tunnel. Нужно для старого API /connect с dest_host.
	return s.BindDialer(ctx, func(context.Context, string, string, uint16) (ports.Tunnel, error) {
		return tunnel, nil
	})
}

func (s *StackTun) BindDialer(ctx context.Context, dial ports.StreamDialer) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.engine != nil {
		return fmt.Errorf("tun: already bound")
	}
	eng := netstack.NewEngine(s.Device, dial, s.Logger)
	runCtx, cancel := context.WithCancel(ctx)
	s.engine = eng
	s.cancel = cancel
	go func() {
		if err := eng.Run(runCtx); err != nil {
			s.Logger.Warn("tun stack stopped", "error", err)
		}
	}()
	s.Logger.Info("tun: stack bound", "if", s.Device.Name())
	return nil
}

func (s *StackTun) Unbind(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cancel != nil {
		s.cancel()
	}
	var err error
	if s.engine != nil {
		err = s.engine.Close()
		s.engine = nil
	}
	if s.single != nil {
		_ = s.single.Close()
		s.single = nil
	}
	return err
}

func (s *StackTun) Name() string {
	if s.Device == nil {
		return ""
	}
	return s.Device.Name()
}
