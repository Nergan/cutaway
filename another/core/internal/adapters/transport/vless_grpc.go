package transport

import (
	"context"
	"errors"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// ErrNotImplemented возвращается заглушками транспортов, которые в v1 ещё не
// реализованы (см. VLESSGRPCTransport и внутри vless_reality.go).
var ErrNotImplemented = errors.New("transport: not implemented in v1")

// VLESSGRPCTransport — заглушка для VLESS поверх gRPC (альтернатива WS в
// Tier1, см. §9.1 спецификации). Не реализована в v1: gRPC-транспорт в
// sing-box/xray-core построен поверх google.golang.org/grpc +
// google.golang.org/protobuf, а оба модуля резолвятся через домены, не
// входящие в наш сетевой whitelist (google.golang.org), и сами по себе
// значительно тяжелее, чем самодельный HTTP/2-фрейминг вручную. В отличие от
// WebSocket (RFC 6455, ~250 строк), переписывать client-side HTTP/2 + gRPC
// framing с нуля — уже неоправданный объём работы при том, что WS даёт тот
// же результат (маскировка под легитимный CDN-трафик) с кратно меньшей
// сложностью. Если понадобится gRPC конкретно (напр. для обхода DPI, который
// научится отличать WS от HTTP/2) — рекомендуется взять
// google.golang.org/grpc как обычную зависимость в отдельном окружении
// сборки, где proxy.golang.org/google.golang.org доступны.
type VLESSGRPCTransport struct{}

func NewVLESSGRPCTransport() *VLESSGRPCTransport { return &VLESSGRPCTransport{} }

func (t *VLESSGRPCTransport) Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (ports.Tunnel, error) {
	return nil, ErrNotImplemented
}
