package tun

import (
	"log/slog"

	"github.com/another-vpn/another/core/internal/ports"
)

// SelectTun открывает платформенный TUN либо Noop, если устройства нет
// (dev без прав / ANOTHER_ALLOW_NOOP_TUN=1 / платформа вне релиза).
func SelectTun(logger *slog.Logger) ports.TunnelPort {
	if st := NewPlatformTun(logger); st != nil {
		return st
	}
	if logger != nil {
		logger.Warn("tun: using noop (трафик ОС не перехватывается)")
	}
	return NewNoopTun(logger)
}
