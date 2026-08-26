//go:build !linux && !windows && !android

package killswitch

import (
	"log/slog"

	"github.com/another-vpn/another/core/internal/ports"
)

func SelectKillSwitch(logger *slog.Logger) ports.KillSwitchPort {
	return NewNoopKillSwitch(logger)
}
