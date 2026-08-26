// Package ratelimiter содержит реализации ports.RateLimiterPort.
package ratelimiter

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// TokenBucket — шейпер трафика на основе классического token bucket,
// реализованный на чистом stdlib (time/sync). Заменяет golang.org/x/time/rate
// из черновика спецификации (§6) по тем же причинам нулевых внешних
// зависимостей, что и в go.mod: модуль golang.org/x/time резолвится через
// домен golang.org, недоступный в нашем сетевом окружении сборки без
// proxy.golang.org.
//
// Алгоритм: bucket пополняется на ratePerSecond токенов (байт) в секунду, не
// превышая burst. WaitN блокируется, пока не накопится n токенов.
type TokenBucket struct {
	mu sync.Mutex

	ratePerSecond float64 // токенов (байт) в секунду
	burst         float64 // максимальный размер bucket

	tokens   float64
	lastFill time.Time
}

// NewTokenBucket создаёт лимитер. Пример из черновика спецификации —
// 10 Mbps ≈ 1_250_000 байт/сек с запасом burst 2 МБ:
//
//	NewTokenBucket(1_250_000, 2_000_000)
func NewTokenBucket(ratePerSecond, burst float64) *TokenBucket {
	return &TokenBucket{
		ratePerSecond: ratePerSecond,
		burst:         burst,
		tokens:        burst, // стартуем с полного бака, чтобы не душить первый всплеск
		lastFill:      time.Now(),
	}
}

func (t *TokenBucket) refill() {
	now := time.Now()
	elapsed := now.Sub(t.lastFill).Seconds()
	t.lastFill = now
	t.tokens += elapsed * t.ratePerSecond
	if t.tokens > t.burst {
		t.tokens = t.burst
	}
}

// WaitN блокируется, пока не станет доступно n токенов, либо пока не
// отменится ctx. Реализовано через короткий поллинг (10мс), а не через
// один большой time.Sleep, чтобы вовремя реагировать на отмену контекста.
func (t *TokenBucket) WaitN(ctx context.Context, n int) error {
	if float64(n) > t.burst {
		return fmt.Errorf("ratelimiter: request for %d tokens exceeds burst capacity %.0f", n, t.burst)
	}

	const pollInterval = 10 * time.Millisecond
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		t.mu.Lock()
		t.refill()
		if t.tokens >= float64(n) {
			t.tokens -= float64(n)
			t.mu.Unlock()
			return nil
		}
		t.mu.Unlock()

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			// попробовать снова на следующей итерации
		}
	}
}
