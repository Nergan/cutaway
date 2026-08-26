package ratelimiter

import (
	"context"
	"testing"
	"time"
)

func TestTokenBucket_AllowsWithinBurst(t *testing.T) {
	tb := NewTokenBucket(1000, 500) // 1000 B/s, burst 500 B

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	start := time.Now()
	if err := tb.WaitN(ctx, 400); err != nil {
		t.Fatalf("WaitN: %v", err)
	}
	if elapsed := time.Since(start); elapsed > 50*time.Millisecond {
		t.Errorf("WaitN within burst took too long: %v", elapsed)
	}
}

func TestTokenBucket_BlocksUntilRefill(t *testing.T) {
	tb := NewTokenBucket(1000, 300) // 1000 B/s, burst 300 B

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	// Исчерпываем почти весь бак, оставляя 50 токенов свободными.
	if err := tb.WaitN(ctx, 250); err != nil {
		t.Fatalf("first WaitN: %v", err)
	}

	// Следующий запрос на 200 байт (в пределах burst=300, но бак почти пуст)
	// при скорости 1000 Б/с должен занять заметное время (~150мс на
	// недостающие 150 байт), т.к. нужно дождаться пополнения.
	start := time.Now()
	if err := tb.WaitN(ctx, 200); err != nil {
		t.Fatalf("second WaitN: %v", err)
	}
	elapsed := time.Since(start)
	if elapsed < 100*time.Millisecond {
		t.Errorf("expected WaitN to block for refill, took only %v", elapsed)
	}
}

func TestTokenBucket_RejectsRequestLargerThanBurst(t *testing.T) {
	tb := NewTokenBucket(1000, 100)
	err := tb.WaitN(context.Background(), 1000)
	if err == nil {
		t.Fatal("expected error for request exceeding burst capacity")
	}
}

func TestTokenBucket_RespectsContextCancellation(t *testing.T) {
	tb := NewTokenBucket(1, 10) // очень медленное пополнение
	// сначала исчерпываем бак
	_ = tb.WaitN(context.Background(), 10)

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	err := tb.WaitN(ctx, 10)
	if err != context.DeadlineExceeded {
		t.Errorf("err = %v, want context.DeadlineExceeded", err)
	}
}
