//go:build !linux && !windows && !android

package tun

import "log/slog"

func NewPlatformTun(logger *slog.Logger) *StackTun {
	if logger != nil {
		logger.Info("tun: платформа вне релиза, используйте NoopTun")
	}
	return nil
}
