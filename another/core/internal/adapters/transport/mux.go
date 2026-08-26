package transport

import (
	"context"
	"fmt"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// MuxTransport выбирает адаптер по node.Transport. Tier1 (WS) остаётся
// на crypto/tls; Reality тянет uTLS только на своём пути.
type MuxTransport struct {
	WS      *VLESSWebSocketTransport
	XHTTP   *VLESSXHTTPTransport
	Reality *VLESSRealityTransport
	GRPC    *VLESSGRPCTransport
	Echo    *EchoTransport
}

func NewMuxTransport() *MuxTransport {
	return &MuxTransport{
		WS:      NewVLESSWebSocketTransport(),
		XHTTP:   NewVLESSXHTTPTransport(),
		Reality: NewVLESSRealityTransport(),
		GRPC:    NewVLESSGRPCTransport(),
		Echo:    NewEchoTransport(),
	}
}

func (m *MuxTransport) Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (ports.Tunnel, error) {
	switch node.Transport {
	case domain.TransportVLESSWebSocket:
		return m.WS.Dial(ctx, node, creds, destHost, destPort)
	case domain.TransportVLESSXHTTP:
		return m.XHTTP.Dial(ctx, node, creds, destHost, destPort)
	case domain.TransportVLESSReality:
		return m.Reality.Dial(ctx, node, creds, destHost, destPort)
	case domain.TransportVLESSGRPC:
		return m.GRPC.Dial(ctx, node, creds, destHost, destPort)
	case domain.TransportEcho:
		return m.Echo.Dial(ctx, node, creds, destHost, destPort)
	default:
		return nil, fmt.Errorf("transport: unknown kind %s", node.Transport)
	}
}
