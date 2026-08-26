package ports

import (
	"context"

	"github.com/another-vpn/another/core/internal/domain"
)

// ProbePort меряет доступность входов (TCP connect, опционально TLS).
// Нужен, чтобы failover менял не только hostname, но и выбирал живой
// вход по RTT — условие вайтлиста, не «оптимизация».
type ProbePort interface {
	Probe(ctx context.Context, nodes []domain.NodeDescriptor) []domain.ProbeResult
}
