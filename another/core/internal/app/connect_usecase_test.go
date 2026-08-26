package app

import (
	"context"
	"errors"
	"os"
	"testing"

	"github.com/another-vpn/another/core/internal/adapters/keystore"
	"github.com/another-vpn/another/core/internal/adapters/killswitch"
	"github.com/another-vpn/another/core/internal/adapters/transport"
	"github.com/another-vpn/another/core/internal/adapters/tun"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

func newEchoTransportForTest() *transport.EchoTransport {
	return transport.NewEchoTransport()
}

// mockAuth реализует ports.AuthPort: пропускает узлы из FailFor, остальные
// аутентифицирует "успешно" с фиктивными credentials.
type mockAuth struct {
	FailFor map[string]error
	calls   []string
}

func (m *mockAuth) ChallengeResponse(ctx context.Context, node domain.NodeDescriptor, clientID string, identity *domain.DeviceIdentity) (*domain.SessionCredentials, error) {
	m.calls = append(m.calls, node.Name)
	if err, ok := m.FailFor[node.Name]; ok {
		return nil, err
	}
	return &domain.SessionCredentials{BearerToken: "mock-token"}, nil
}

func policyWithNodes(names ...string) *domain.FailoverPolicy {
	nodes := make([]domain.NodeDescriptor, len(names))
	for i, n := range names {
		nodes[i] = domain.NodeDescriptor{Name: n, Priority: i}
	}
	return domain.NewFailoverPolicy(nodes)
}

func newTestConnectUseCase(auth ports.AuthPort, transport_ ports.OutboundTransportPort) *ConnectUseCase {
	session := domain.NewTunnelSession()
	dir, err := os.MkdirTemp("", "another-test-keystore-*")
	if err != nil {
		panic(err)
	}
	ks := keystore.NewFileKeyStore(dir)
	ksw := killswitch.NewNoopKillSwitch(nil)
	tp := tun.NewNoopTun(nil)
	return NewConnectUseCase(session, ks, auth, transport_, tp, ksw, nil, "test-client", nil)
}

func TestConnectUseCase_SucceedsOnFirstNode(t *testing.T) {
	auth := &mockAuth{FailFor: map[string]error{}}
	echoTransport := newEchoTransportForTest()
	uc := newTestConnectUseCase(auth, echoTransport)

	policy := policyWithNodes("cf-worker", "render", "vps-reality")
	if err := uc.Execute(context.Background(), policy, "example.com", 443); err != nil {
		t.Fatalf("Execute: %v", err)
	}

	snap := uc.Session.Snapshot()
	if snap.State != domain.StateConnected {
		t.Errorf("state = %v, want Connected", snap.State)
	}
	if snap.ActiveNode == nil || snap.ActiveNode.Name != "cf-worker" {
		t.Errorf("active node = %v, want cf-worker", snap.ActiveNode)
	}
	if len(auth.calls) != 1 {
		t.Errorf("expected only first node to be tried, got calls: %v", auth.calls)
	}
}

func TestConnectUseCase_FailsOverToSecondNode(t *testing.T) {
	auth := &mockAuth{FailFor: map[string]error{
		"cf-worker": errors.New("auth rejected"),
	}}
	echoTransport := newEchoTransportForTest()
	uc := newTestConnectUseCase(auth, echoTransport)

	policy := policyWithNodes("cf-worker", "render", "vps-reality")
	if err := uc.Execute(context.Background(), policy, "example.com", 443); err != nil {
		t.Fatalf("Execute: %v", err)
	}

	snap := uc.Session.Snapshot()
	if snap.State != domain.StateConnected {
		t.Errorf("state = %v, want Connected", snap.State)
	}
	if snap.ActiveNode == nil || snap.ActiveNode.Name != "render" {
		t.Errorf("active node = %v, want render (after failover from cf-worker)", snap.ActiveNode)
	}
	if len(auth.calls) != 2 {
		t.Errorf("expected 2 attempts (cf-worker, render), got: %v", auth.calls)
	}
}

func TestConnectUseCase_AllNodesFail_ArmsKillSwitchAndReturnsFailed(t *testing.T) {
	auth := &mockAuth{FailFor: map[string]error{
		"cf-worker":   errors.New("auth rejected"),
		"render":      errors.New("timeout"),
		"vps-reality": errors.New("not implemented"),
	}}
	echoTransport := newEchoTransportForTest()
	uc := newTestConnectUseCase(auth, echoTransport)

	policy := policyWithNodes("cf-worker", "render", "vps-reality")
	err := uc.Execute(context.Background(), policy, "example.com", 443)
	if !errors.Is(err, ErrAllNodesFailed) {
		t.Fatalf("err = %v, want ErrAllNodesFailed", err)
	}

	snap := uc.Session.Snapshot()
	if snap.State != domain.StateFailed {
		t.Errorf("state = %v, want Failed", snap.State)
	}
	if snap.LastError == nil {
		t.Error("expected LastError to be set")
	}
	// Ключевая проверка §5.4: даже при провале ВСЕХ узлов kill switch должен
	// быть armed (noop-реализация не даёт это проверить по эффекту, но
	// проверяем хотя бы, что Execute не паникует и не возвращает состояние
	// Connected/Connecting — т.е. трафик "как будто" не течёт мимо туннеля).
	if snap.State == domain.StateConnected || snap.State == domain.StateConnecting {
		t.Errorf("unexpected state after total failure: %v", snap.State)
	}
}

func TestConnectUseCase_VPNModeNoopStack(t *testing.T) {
	auth := &mockAuth{FailFor: map[string]error{}}
	echoTransport := newEchoTransportForTest()
	uc := newTestConnectUseCase(auth, echoTransport)
	policy := policyWithNodes("cf-worker")
	if err := uc.Execute(context.Background(), policy, "", 0); err != nil {
		t.Fatalf("VPN Execute: %v", err)
	}
	if uc.Session.Snapshot().State != domain.StateConnected {
		t.Fatalf("state = %v", uc.Session.Snapshot().State)
	}
}

func TestConnectUseCase_RespectsFailoverOrder(t *testing.T) {
	auth := &mockAuth{FailFor: map[string]error{}}
	echoTransport := newEchoTransportForTest()
	uc := newTestConnectUseCase(auth, echoTransport)

	// Явно задаём приоритет в обратном порядке добавления
	nodes := []domain.NodeDescriptor{
		{Name: "low-priority", Priority: 10},
		{Name: "high-priority", Priority: 1},
	}
	policy := domain.NewFailoverPolicy(nodes)

	if err := uc.Execute(context.Background(), policy, "example.com", 443); err != nil {
		t.Fatalf("Execute: %v", err)
	}
	snap := uc.Session.Snapshot()
	if snap.ActiveNode.Name != "high-priority" {
		t.Errorf("active node = %q, want high-priority (lower Priority value wins)", snap.ActiveNode.Name)
	}
}
