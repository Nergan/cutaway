//go:build !android

package tun

import (
	"fmt"
	"log/slog"
)

// NewAndroidTunFromFD на не-Android только чтобы cmd/mobilelib собирался в тестах.
func NewAndroidTunFromFD(fd int, logger *slog.Logger) (*StackTun, error) {
	return nil, fmt.Errorf("tun: android fd %d is only valid on android", fd)
}
