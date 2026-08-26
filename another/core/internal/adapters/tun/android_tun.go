//go:build android

package tun

import (
	"fmt"
	"log/slog"
	"os"
)

// AndroidTun читает fd, полученный из VpnService.Builder.establish().
// Сам интерфейс и kill switch создаёт Kotlin (фаза 3 — тонкий мост).
func NewAndroidTunFromFD(fd int, logger *slog.Logger) (*StackTun, error) {
	if fd <= 0 {
		return nil, fmt.Errorf("tun: invalid vpn fd %d", fd)
	}
	f := os.NewFile(uintptr(fd), "vpn-tun")
	if f == nil {
		return nil, fmt.Errorf("tun: os.NewFile(%d) failed", fd)
	}
	return NewStackTun(&filePacket{f: f, name: "tun0"}, logger), nil
}

func NewPlatformTun(logger *slog.Logger) *StackTun {
	// Без fd от VpnService открыть TUN из Go нельзя.
	if logger != nil {
		logger.Info("android tun: wait for SetTunFd from VpnService")
	}
	return nil
}
