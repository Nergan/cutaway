//go:build linux && !android

package tun

import (
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"syscall"
	"unsafe"
)

const (
	iffTUN    = 0x0001
	iffNoPI   = 0x1000
	tunsetiff = 0x400454ca
	ifnamsiz  = 16
)

type ifReq struct {
	Name  [ifnamsiz]byte
	Flags uint16
	pad   [22]byte
}

// LinuxTun — /dev/net/tun, IFF_TUN|IFF_NO_PI. Нужен CAP_NET_ADMIN.
// Адрес 10.7.0.2/24, маршруты 0.0.0.0/1 и 128.0.0.0/1 (как WireGuard).
type LinuxTun struct {
	*StackTun
	ifName string
}

func OpenLinuxTun(ifName string, logger *slog.Logger) (*LinuxTun, error) {
	if ifName == "" {
		ifName = "another0"
	}
	f, err := os.OpenFile("/dev/net/tun", os.O_RDWR, 0)
	if err != nil {
		return nil, fmt.Errorf("tun: open /dev/net/tun: %w", err)
	}
	var req ifReq
	copy(req.Name[:], ifName)
	req.Flags = iffTUN | iffNoPI
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), tunsetiff, uintptr(unsafe.Pointer(&req)))
	if errno != 0 {
		_ = f.Close()
		return nil, fmt.Errorf("tun: TUNSETIFF: %v", errno)
	}
	if err := configureLinuxIface(ifName); err != nil {
		_ = f.Close()
		return nil, err
	}
	dev := &filePacket{f: f, name: ifName}
	return &LinuxTun{StackTun: NewStackTun(dev, logger), ifName: ifName}, nil
}

func configureLinuxIface(name string) error {
	cmds := [][]string{
		{"ip", "addr", "add", "10.7.0.2/24", "dev", name},
		{"ip", "link", "set", name, "up"},
		{"ip", "route", "add", "0.0.0.0/1", "dev", name},
		{"ip", "route", "add", "128.0.0.0/1", "dev", name},
	}
	for _, c := range cmds {
		cmd := exec.Command(c[0], c[1:]...)
		out, err := cmd.CombinedOutput()
		if err != nil {
			return fmt.Errorf("tun: %v: %w (%s)", c, err, out)
		}
	}
	return nil
}
