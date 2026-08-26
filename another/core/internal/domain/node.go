package domain

import (
	"encoding/json"
	"fmt"
)

// Tier различает два эксплуатационных уровня системы (см. §3 спецификации):
// Tier1 — bootstrap на бесплатной инфраструктуре (Cloudflare Worker VLESS-WS,
// Render sing-box), Tier2 — целевое состояние (выделенный VPS,
// VLESS-Reality). Явное разделение — одна из правок относительно черновика,
// где протокол Reality был смешан с Tier1-инфраструктурой, хотя технически
// не может работать внутри V8-изолята Cloudflare Workers.
type Tier int

const (
	Tier1Bootstrap Tier = iota
	Tier2Target
)

func (t Tier) String() string {
	switch t {
	case Tier1Bootstrap:
		return "tier1-bootstrap"
	case Tier2Target:
		return "tier2-target"
	default:
		return "unknown"
	}
}

func parseTier(s string) (Tier, error) {
	switch s {
	case "tier1-bootstrap":
		return Tier1Bootstrap, nil
	case "tier2-target":
		return Tier2Target, nil
	default:
		return 0, fmt.Errorf("domain: unknown tier %q", s)
	}
}

// MarshalJSON/UnmarshalJSON — Tier пересекает границу процесса (Flutter →
// Core через локальный control API/FFI, см. §6.1 спецификации, и edge/ →
// Flutter при онбординге, см. edge/src/handlers/enroll.ts) как строка
// ("tier1-bootstrap"), а не как сырое число — используется тот же
// текстовый вид, что и String(), а не отдельный набор констант, чтобы
// логи и JSON-провод не расходились в терминологии.
func (t Tier) MarshalJSON() ([]byte, error) {
	return json.Marshal(t.String())
}

func (t *Tier) UnmarshalJSON(data []byte) error {
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	parsed, err := parseTier(s)
	if err != nil {
		return err
	}
	*t = parsed
	return nil
}

// TransportKind — какой адаптер OutboundTransportPort использовать для узла.
type TransportKind int

const (
	TransportVLESSWebSocket TransportKind = iota
	TransportVLESSGRPC
	TransportVLESSReality
	TransportVLESSXHTTP
	TransportEcho // dev/test-петля, см. adapters/transport/echo_transport.go
)

func (k TransportKind) String() string {
	switch k {
	case TransportVLESSWebSocket:
		return "vless-ws"
	case TransportVLESSGRPC:
		return "vless-grpc"
	case TransportVLESSReality:
		return "vless-reality"
	case TransportVLESSXHTTP:
		return "vless-xhttp"
	case TransportEcho:
		return "echo"
	default:
		return "unknown"
	}
}

func parseTransportKind(s string) (TransportKind, error) {
	switch s {
	case "vless-ws":
		return TransportVLESSWebSocket, nil
	case "vless-grpc":
		return TransportVLESSGRPC, nil
	case "vless-reality":
		return TransportVLESSReality, nil
	case "vless-xhttp":
		return TransportVLESSXHTTP, nil
	case "echo":
		return TransportEcho, nil
	default:
		return 0, fmt.Errorf("domain: unknown transport kind %q", s)
	}
}

func (k TransportKind) MarshalJSON() ([]byte, error) {
	return json.Marshal(k.String())
}

func (k *TransportKind) UnmarshalJSON(data []byte) error {
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	parsed, err := parseTransportKind(s)
	if err != nil {
		return err
	}
	*k = parsed
	return nil
}

// NodeDescriptor описывает одну точку входа, между которыми происходит
// failover (см. app.ConnectUseCase). JSON-теги в snake_case — тот же
// формат, что уже используется в edge/wrangler.toml (NODES_JSON) и в
// ответе edge/src/handlers/enroll.ts, чтобы Flutter могло десериализовать
// один и тот же JSON что от edge/, что при передаче в Core без конвертации
// имён полей на границе.
type NodeDescriptor struct {
	Name         string        `json:"name"` // человекочитаемое имя, для логов/UI
	Tier         Tier          `json:"tier"`
	Transport    TransportKind `json:"transport"`
	Host         string        `json:"host"` // адрес сервера (для WS — Cloudflare Worker/Render хост)
	Port         uint16        `json:"port"`
	Path         string        `json:"path"`          // путь WS-апгрейда, напр. "/proxy"
	SNI          string        `json:"sni,omitempty"` // server_name / SNI-донор (важно для Reality, см. §9.2)
	Priority     int           `json:"priority"`      // меньше — выше приоритет при выборе узла
	ControlPlane string        `json:"control_plane"` // базовый URL control-plane для challenge-response (§7.2)

	// Reality (Tier2). Hex X25519 public сервера и shortId 0–16 hex.
	// Пустые на Tier1. См. docs/circumvention.md и адаптер vless_reality.
	RealityPublicKey string `json:"reality_public_key,omitempty"`
	ShortID          string `json:"short_id,omitempty"`
	Fingerprint      string `json:"fingerprint,omitempty"` // chrome (uTLS), по умолчанию chrome
}
