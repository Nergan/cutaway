package ports

import "context"

// RateLimiterPort — driven-порт для шейпинга трафика до инкапсуляции в
// туннель (см. §6 спецификации). В черновике использовался внешний пакет
// golang.org/x/time/rate; в v1 заменён на реализацию на чистом stdlib
// (adapters/ratelimiter/token_bucket.go) по тем же причинам нулевых внешних
// зависимостей, что и в go.mod.
type RateLimiterPort interface {
	// WaitN блокируется, пока не станет доступно n "токенов" (байт), либо
	// пока не отменится ctx.
	WaitN(ctx context.Context, n int) error
}
