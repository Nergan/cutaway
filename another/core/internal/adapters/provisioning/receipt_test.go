package provisioning

import (
	"path/filepath"
	"testing"

	"github.com/another-vpn/another/core/internal/domain"
)

func TestReceiptRoundTrip(t *testing.T) {
	dir := t.TempDir()
	_, ok, err := LoadReceipt(dir)
	if err != nil || ok {
		t.Fatalf("empty dir: ok=%v err=%v", ok, err)
	}
	want := Receipt{
		ClientID: "nu-ya-1",
		Nodes: []domain.NodeDescriptor{{
			Name: "cf-worker", ControlPlane: "https://edge.example", Host: "edge.example", Port: 443,
		}},
	}
	if err := SaveReceipt(dir, want); err != nil {
		t.Fatal(err)
	}
	got, ok, err := LoadReceipt(dir)
	if err != nil || !ok {
		t.Fatalf("ok=%v err=%v", ok, err)
	}
	if got.ClientID != want.ClientID || got.Nodes[0].ControlPlane != want.Nodes[0].ControlPlane {
		t.Fatalf("got=%+v", got)
	}
	if filepath.Base(ReceiptPath(dir)) != receiptName {
		t.Fatal("path")
	}
}
