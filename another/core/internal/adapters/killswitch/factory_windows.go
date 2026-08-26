//go:build windows

package killswitch

import (
	"log/slog"
	"os"

	"github.com/another-vpn/another/core/internal/ports"
)

func SelectKillSwitch(logger *slog.Logger) ports.KillSwitchPort {
	if os.Getenv("ANOTHER_KILLSWITCH") == "noop" || os.Getenv("ANOTHER_ALLOW_NOOP_TUN") == "1" {
		return NewNoopKillSwitch(logger)
	}
	return NewWindowsKillSwitch()
}
