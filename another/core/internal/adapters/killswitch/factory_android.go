//go:build android

package killswitch

import (
	"log/slog"

	"github.com/another-vpn/another/core/internal/ports"
)

func SelectKillSwitch(logger *slog.Logger) ports.KillSwitchPort {
	return NewAndroidKillSwitch(logger)
}
