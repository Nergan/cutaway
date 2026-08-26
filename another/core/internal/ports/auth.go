package ports

import (
	"context"

	"github.com/another-vpn/another/core/internal/domain"
)

// AuthPort — driven-порт для challenge-response аутентификации на
// control-plane (см. §7.2 спецификации: GET /nonce → подпись → POST /auth →
// session_token). Реализация: adapters/auth/http_challenge.go.
type AuthPort interface {
	// ChallengeResponse выполняет полный цикл аутентификации для узла node и
	// возвращает SessionCredentials, которыми OutboundTransportPort
	// сопровождает VLESS-подключение. clientID — серверный идентификатор
	// (присвоенный при онбординге, §7.1), передаётся отдельно от identity:
	// сама криптографическая идентичность не привязана к client_id
	// (см. domain.DeviceIdentity про причину).
	ChallengeResponse(ctx context.Context, node domain.NodeDescriptor, clientID string, identity *domain.DeviceIdentity) (*domain.SessionCredentials, error)
}
