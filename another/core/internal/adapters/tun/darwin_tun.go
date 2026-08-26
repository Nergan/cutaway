//go:build darwin

package tun

import (
	"context"
	"errors"

	"github.com/another-vpn/another/core/internal/ports"
)

// DarwinTun — TODO v2. utun на macOS доступен через обычный BSD-сокет
// (PF_SYSTEM/SYSPROTO_CONTROL + ioctl CTLIOCGINFO), полностью реализуемо на
// чистом stdlib через syscall без cgo — это один из немногих платформенных
// TUN-адаптеров, для которого не нужны сторонние зависимости или platform
// SDK, поэтому в v2 имеет смысл реализовать его в первую очередь среди
// десктопных платформ.
type DarwinTun struct{}

func NewDarwinTun() *DarwinTun { return &DarwinTun{} }

var errNotImplementedDarwinTun = errors.New("tun: utun-based TUN not implemented in v1 (see darwin_tun.go)")

func (d *DarwinTun) Bind(ctx context.Context, tunnel ports.Tunnel) error {
	return errNotImplementedDarwinTun
}
func (d *DarwinTun) Unbind(ctx context.Context) error { return errNotImplementedDarwinTun }
