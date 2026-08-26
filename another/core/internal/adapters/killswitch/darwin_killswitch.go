//go:build darwin

package killswitch

import (
	"context"
	"errors"
)

// DarwinKillSwitch — TODO v2. На macOS реализуется через pf (Packet Filter)
// anchor-правила: Arm() должен добавить anchor, блокирующий весь исходящий
// трафик кроме loopback и через utun-интерфейс (см. §6 спецификации:
// utun доступен через syscall без cgo, но управление pf идёт через
// вызовы ioctl к /dev/pf, что требует привилегий root — процесс должен
// быть запущен как daemon с повышенными правами, либо использовать
// SMAppService/priv-helper на современном macOS).
type DarwinKillSwitch struct{}

func NewDarwinKillSwitch() *DarwinKillSwitch { return &DarwinKillSwitch{} }

var errNotImplementedDarwin = errors.New("killswitch: pf-based kill switch not implemented in v1 (see darwin_killswitch.go)")

func (d *DarwinKillSwitch) Arm(ctx context.Context) error             { return errNotImplementedDarwin }
func (d *DarwinKillSwitch) Disarm(ctx context.Context) error          { return errNotImplementedDarwin }
func (d *DarwinKillSwitch) OnTunnelDropped(ctx context.Context) error { return errNotImplementedDarwin }
