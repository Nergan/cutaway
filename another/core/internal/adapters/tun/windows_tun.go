//go:build windows

package tun

import (
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"syscall"
	"unsafe"
)

// Wintun DLL: https://www.wintun.net/ — кладётся рядом с exe (не в git).
// API вызывается через syscall, без cgo.

type wintunDLL struct {
	create, close, start, end, recv, rel, alloc, send, wait, luid *syscall.LazyProc
}

func loadWintun() (*wintunDLL, error) {
	mod := syscall.NewLazyDLL("wintun.dll")
	if err := mod.Load(); err != nil {
		return nil, fmt.Errorf("tun: wintun.dll not found (скачайте с wintun.net и положите рядом с another-core): %w", err)
	}
	return &wintunDLL{
		create: mod.NewProc("WintunCreateAdapter"),
		close:  mod.NewProc("WintunCloseAdapter"),
		start:  mod.NewProc("WintunStartSession"),
		end:    mod.NewProc("WintunEndSession"),
		recv:   mod.NewProc("WintunReceivePacket"),
		rel:    mod.NewProc("WintunReleaseReceivePacket"),
		alloc:  mod.NewProc("WintunAllocateSendPacket"),
		send:   mod.NewProc("WintunSendPacket"),
		wait:   mod.NewProc("WintunGetReadWaitEvent"),
		luid:   mod.NewProc("WintunGetAdapterLUID"),
	}, nil
}

type wintunDevice struct {
	dll     *wintunDLL
	adapter uintptr
	session uintptr
	name    string
}

func (w *wintunDevice) Name() string { return w.name }

func (w *wintunDevice) ReadPacket(buf []byte) (int, error) {
	var size uint32
	for {
		pkt, _, _ := w.dll.recv.Call(w.session, uintptr(unsafe.Pointer(&size)))
		if pkt != 0 {
			n := int(size)
			if n > len(buf) {
				n = len(buf)
			}
			readFromUintptr(pkt, buf[:n])
			w.dll.rel.Call(w.session, pkt)
			return n, nil
		}
		ev, _, _ := w.dll.wait.Call(w.session)
		if ev == 0 {
			return 0, fmt.Errorf("tun: wintun wait event missing")
		}
		syscall.WaitForSingleObject(syscall.Handle(ev), syscall.INFINITE)
	}
}

func (w *wintunDevice) WritePacket(pkt []byte) error {
	mem, _, _ := w.dll.alloc.Call(w.session, uintptr(len(pkt)))
	if mem == 0 {
		return fmt.Errorf("tun: WintunAllocateSendPacket failed")
	}
	writeToUintptr(mem, pkt)
	w.dll.send.Call(w.session, mem)
	return nil
}

//go:nocheckptr
func readFromUintptr(p uintptr, dst []byte) {
	for i := range dst {
		dst[i] = *(*byte)(unsafe.Pointer(p + uintptr(i)))
	}
}

//go:nocheckptr
func writeToUintptr(p uintptr, src []byte) {
	for i, b := range src {
		*(*byte)(unsafe.Pointer(p + uintptr(i))) = b
	}
}

func (w *wintunDevice) Close() error {
	if w.session != 0 {
		w.dll.end.Call(w.session)
		w.session = 0
	}
	if w.adapter != 0 {
		w.dll.close.Call(w.adapter)
		w.adapter = 0
	}
	return nil
}

func OpenWindowsTun(logger *slog.Logger) (*StackTun, error) {
	dll, err := loadWintun()
	if err != nil {
		return nil, err
	}
	name, err := syscall.UTF16PtrFromString("Another")
	if err != nil {
		return nil, err
	}
	typ, err := syscall.UTF16PtrFromString("Another")
	if err != nil {
		return nil, err
	}
	adapter, _, callErr := dll.create.Call(uintptr(unsafe.Pointer(name)), uintptr(unsafe.Pointer(typ)), 0)
	if adapter == 0 {
		return nil, fmt.Errorf("tun: WintunCreateAdapter: %v", callErr)
	}
	const ringCap = 0x400000
	session, _, callErr := dll.start.Call(adapter, ringCap)
	if session == 0 {
		dll.close.Call(adapter)
		return nil, fmt.Errorf("tun: WintunStartSession: %v", callErr)
	}
	dev := &wintunDevice{dll: dll, adapter: adapter, session: session, name: "Another"}
	if err := configureWindowsIface("Another"); err != nil {
		_ = dev.Close()
		return nil, err
	}
	return NewStackTun(dev, logger), nil
}

func configureWindowsIface(name string) error {
	cmds := [][]string{
		{"netsh", "interface", "ip", "set", "address", "name=" + name, "source=static", "addr=10.7.0.2", "mask=255.255.255.0"},
		{"netsh", "interface", "ipv4", "add", "route", "0.0.0.0/1", name},
		{"netsh", "interface", "ipv4", "add", "route", "128.0.0.0/1", name},
	}
	for _, c := range cmds {
		out, err := exec.Command(c[0], c[1:]...).CombinedOutput()
		if err != nil {
			return fmt.Errorf("tun: %v: %w (%s)", c, err, out)
		}
	}
	return nil
}

func NewPlatformTun(logger *slog.Logger) *StackTun {
	if os.Getenv("ANOTHER_TUN") == "noop" || os.Getenv("ANOTHER_ALLOW_NOOP_TUN") == "1" {
		return nil
	}
	st, err := OpenWindowsTun(logger)
	if err != nil {
		if logger != nil {
			logger.Warn("windows tun unavailable", "error", err)
		}
		return nil
	}
	return st
}
