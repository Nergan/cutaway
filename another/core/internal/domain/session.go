package domain

import (
	"sync"
	"time"
)

// SessionState — состояния машины состояний туннеля (см. §5.4 спецификации,
// используется также KillSwitchPort'ом для решения, когда блокировать
// трафик мимо туннеля).
type SessionState int

const (
	StateDisconnected SessionState = iota
	StateConnecting
	StateConnected
	StateReconnecting
	StateFailed
)

func (s SessionState) String() string {
	switch s {
	case StateDisconnected:
		return "disconnected"
	case StateConnecting:
		return "connecting"
	case StateConnected:
		return "connected"
	case StateReconnecting:
		return "reconnecting"
	case StateFailed:
		return "failed"
	default:
		return "unknown"
	}
}

// TunnelSession — единственный агрегат, владеющий текущим состоянием
// подключения. Потокобезопасен, т.к. к нему обращаются одновременно
// use-case (пишет) и слой статуса, который GUI опрашивает по HTTP/FFI
// (читает) — см. cmd/desktop/main.go.
type TunnelSession struct {
	mu         sync.RWMutex
	state      SessionState
	activeNode *NodeDescriptor
	startedAt  time.Time
	lastError  error
	bytesSent  uint64
	bytesRecv  uint64
}

func NewTunnelSession() *TunnelSession {
	return &TunnelSession{state: StateDisconnected}
}

func (s *TunnelSession) SetConnecting() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = StateConnecting
	s.lastError = nil
}

func (s *TunnelSession) SetConnected(node *NodeDescriptor) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = StateConnected
	s.activeNode = node
	s.startedAt = time.Now()
	s.lastError = nil
}

func (s *TunnelSession) SetReconnecting() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = StateReconnecting
}

func (s *TunnelSession) SetFailed(err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = StateFailed
	s.lastError = err
}

func (s *TunnelSession) SetDisconnected() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = StateDisconnected
	s.activeNode = nil
	s.lastError = nil
}

func (s *TunnelSession) AddBytes(sent, recv uint64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.bytesSent += sent
	s.bytesRecv += recv
}

// Snapshot — иммутабельный слепок состояния для чтения из GUI/CLI.
type Snapshot struct {
	State      SessionState
	ActiveNode *NodeDescriptor
	StartedAt  time.Time
	LastError  error
	BytesSent  uint64
	BytesRecv  uint64
}

func (s *TunnelSession) Snapshot() Snapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return Snapshot{
		State:      s.state,
		ActiveNode: s.activeNode,
		StartedAt:  s.startedAt,
		LastError:  s.lastError,
		BytesSent:  s.bytesSent,
		BytesRecv:  s.bytesRecv,
	}
}
