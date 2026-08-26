//go:build linux && !android

package tun

import (
	"log/slog"
	"os"
)

func NewPlatformTun(logger *slog.Logger) *StackTun {
	if os.Getenv("ANOTHER_TUN") == "noop" || os.Getenv("ANOTHER_ALLOW_NOOP_TUN") == "1" {
		// StackTun с nil Device нельзя; для noop см. NewNoopTun.
		return nil
	}
	lt, err := OpenLinuxTun(os.Getenv("ANOTHER_TUN_IF"), logger)
	if err != nil {
		if logger != nil {
			logger.Warn("linux tun unavailable", "error", err)
		}
		return nil
	}
	return lt.StackTun
}
