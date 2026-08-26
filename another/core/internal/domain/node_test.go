package domain

import (
	"encoding/json"
	"testing"
)

func TestNodeDescriptor_JSONRoundTrip(t *testing.T) {
	original := NodeDescriptor{
		Name:         "cf-worker",
		Tier:         Tier1Bootstrap,
		Transport:    TransportVLESSWebSocket,
		Host:         "cf-worker.another.example",
		Port:         443,
		Path:         "/proxy",
		Priority:     1,
		ControlPlane: "https://cf-worker.another.example",
	}

	raw, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}

	var decoded NodeDescriptor
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}

	if decoded != original {
		t.Errorf("round-trip mismatch:\n got  %+v\n want %+v", decoded, original)
	}
}

func TestNodeDescriptor_UnmarshalsEdgeNodesJSONFormat(t *testing.T) {
	// Тот же формат, что реально отдаёт edge/wrangler.toml (NODES_JSON) и
	// edge/src/handlers/enroll.ts — сверка форматов на границе Go/TS.
	raw := `{"name":"cf-worker","tier":"tier1-bootstrap","transport":"vless-ws","host":"cf-worker.another.example","port":443,"path":"/proxy","priority":1}`

	var node NodeDescriptor
	if err := json.Unmarshal([]byte(raw), &node); err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}

	if node.Name != "cf-worker" {
		t.Errorf("Name = %q, want cf-worker", node.Name)
	}
	if node.Tier != Tier1Bootstrap {
		t.Errorf("Tier = %v, want Tier1Bootstrap", node.Tier)
	}
	if node.Transport != TransportVLESSWebSocket {
		t.Errorf("Transport = %v, want TransportVLESSWebSocket", node.Transport)
	}
	if node.Port != 443 {
		t.Errorf("Port = %d, want 443", node.Port)
	}
}

func TestNodeDescriptor_UnmarshalsArray(t *testing.T) {
	raw := `[
		{"name":"cf-worker","tier":"tier1-bootstrap","transport":"vless-ws","host":"a.example","port":443,"path":"/proxy","priority":1},
		{"name":"render","tier":"tier1-bootstrap","transport":"vless-ws","host":"b.example","port":443,"path":"/proxy","priority":2}
	]`

	var nodes []NodeDescriptor
	if err := json.Unmarshal([]byte(raw), &nodes); err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}
	if len(nodes) != 2 {
		t.Fatalf("len(nodes) = %d, want 2", len(nodes))
	}
	if nodes[0].Name != "cf-worker" || nodes[1].Name != "render" {
		t.Errorf("unexpected names: %q, %q", nodes[0].Name, nodes[1].Name)
	}
}

func TestTier_UnmarshalJSON_RejectsUnknown(t *testing.T) {
	var tier Tier
	err := json.Unmarshal([]byte(`"tier99-bogus"`), &tier)
	if err == nil {
		t.Fatal("expected error for unknown tier value")
	}
}

func TestTransportKind_UnmarshalJSON_RejectsUnknown(t *testing.T) {
	var tk TransportKind
	err := json.Unmarshal([]byte(`"vless-quic"`), &tk)
	if err == nil {
		t.Fatal("expected error for unknown transport kind value")
	}
}
