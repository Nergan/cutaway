package bootstrap

import (
	"context"
	"log/slog"
	"testing"

	"github.com/another-vpn/another/core/internal/adapters/provisioning"
	"github.com/another-vpn/another/core/internal/domain"
)

type fakeKS struct{ id *domain.DeviceIdentity }

func (f fakeKS) LoadOrCreateDeviceIdentity() (*domain.DeviceIdentity, error) {
	return f.id, nil
}

type fakeEnroll struct {
	clientID string
	nodes    []domain.NodeDescriptor
	err      error
	calls    int
}

func (f *fakeEnroll) Enroll(ctx context.Context, controlPlane, token, pubHex, pubMLDSAHex string) (string, []domain.NodeDescriptor, error) {
	f.calls++
	return f.clientID, f.nodes, f.err
}

func TestPrepareSessionSkipsWithoutTokenOrReceipt(t *testing.T) {
	id, err := domain.GenerateDeviceIdentity()
	if err != nil {
		t.Fatal(err)
	}
	got, err := PrepareSession(context.Background(), slog.Default(), fakeKS{id}, &fakeEnroll{}, t.TempDir(), provisioning.Bundle{}, "https://edge.example")
	if err != nil {
		t.Fatal(err)
	}
	if got.AutoConnect {
		t.Fatal("lab mode must not auto-connect")
	}
}

func TestPrepareSessionEnrollsOnce(t *testing.T) {
	id, err := domain.GenerateDeviceIdentity()
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	en := &fakeEnroll{
		clientID: "nu-ya-1",
		nodes:    []domain.NodeDescriptor{{Name: "cf-worker", ControlPlane: "https://edge.example", Host: "edge.example", Port: 443}},
	}
	bundle := provisioning.Bundle{EnrollmentToken: "aabbcc"}
	first, err := PrepareSession(context.Background(), slog.Default(), fakeKS{id}, en, dir, bundle, "https://edge.example")
	if err != nil {
		t.Fatal(err)
	}
	if !first.AutoConnect || first.ClientID != "nu-ya-1" || en.calls != 1 {
		t.Fatalf("first=%+v calls=%d", first, en.calls)
	}
	second, err := PrepareSession(context.Background(), slog.Default(), fakeKS{id}, en, dir, bundle, "https://edge.example")
	if err != nil {
		t.Fatal(err)
	}
	if en.calls != 1 {
		t.Fatalf("second enroll call, want 1 got %d", en.calls)
	}
	if second.ClientID != "nu-ya-1" || !second.AutoConnect {
		t.Fatalf("second=%+v", second)
	}
}

func TestPrepareSessionRefusesLoopback(t *testing.T) {
	id, err := domain.GenerateDeviceIdentity()
	if err != nil {
		t.Fatal(err)
	}
	_, err = PrepareSession(context.Background(), slog.Default(), fakeKS{id}, &fakeEnroll{}, t.TempDir(), provisioning.Bundle{EnrollmentToken: "tok"}, "http://127.0.0.1:8787")
	if err == nil {
		t.Fatal("expected loopback error")
	}
}

func TestPrepareSessionUsedTokenNotRetriedFromReceipt(t *testing.T) {
	id, err := domain.GenerateDeviceIdentity()
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	en := &fakeEnroll{err: context.Canceled}
	_, err = PrepareSession(context.Background(), slog.Default(), fakeKS{id}, en, dir, provisioning.Bundle{EnrollmentToken: "used"}, "https://edge.example")
	if err == nil {
		t.Fatal("expected error")
	}
	_, ok, err := provisioning.LoadReceipt(dir)
	if err != nil || ok {
		t.Fatalf("receipt should be absent, ok=%v err=%v", ok, err)
	}
}
