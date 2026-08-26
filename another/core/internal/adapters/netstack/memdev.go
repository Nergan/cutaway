package netstack

import (
	"context"
	"sync"
	"time"

	"github.com/another-vpn/another/core/internal/ports"
)

// MemoryDevice — in-memory TUN для тестов NAT без root.
type MemoryDevice struct {
	toStack   chan []byte
	fromStack chan []byte
	closed    chan struct{}
	once      sync.Once
}

func NewMemoryDevice() *MemoryDevice {
	return &MemoryDevice{
		toStack:   make(chan []byte, 32),
		fromStack: make(chan []byte, 32),
		closed:    make(chan struct{}),
	}
}

func (m *MemoryDevice) Inject(pkt []byte) {
	select {
	case m.toStack <- append([]byte(nil), pkt...):
	case <-m.closed:
	}
}

func (m *MemoryDevice) Receive(timeout time.Duration) ([]byte, bool) {
	t := time.NewTimer(timeout)
	defer t.Stop()
	select {
	case p := <-m.fromStack:
		return p, true
	case <-t.C:
		return nil, false
	case <-m.closed:
		return nil, false
	}
}

func (m *MemoryDevice) ReadPacket(buf []byte) (int, error) {
	select {
	case p := <-m.toStack:
		n := copy(buf, p)
		return n, nil
	case <-m.closed:
		return 0, context.Canceled
	}
}

func (m *MemoryDevice) WritePacket(pkt []byte) error {
	select {
	case m.fromStack <- append([]byte(nil), pkt...):
		return nil
	case <-m.closed:
		return context.Canceled
	}
}

func (m *MemoryDevice) Close() error {
	m.once.Do(func() { close(m.closed) })
	return nil
}

func (m *MemoryDevice) Name() string { return "mem0" }

var _ ports.PacketDevice = (*MemoryDevice)(nil)
