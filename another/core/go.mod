module github.com/another-vpn/another/core

go 1.24

// Фаза 2: узкое исключение из «ноль зависимостей» (docs/adr/0001, 0006).
// circl — ML-DSA-65. utls — только Reality. VLESS-WS остаётся на crypto/tls.
// Не тащим xray-core / sing-box / gVisor.

require (
	github.com/cloudflare/circl v1.6.1
	github.com/refraction-networking/utls v1.8.1
	golang.org/x/crypto v0.36.0
)

require (
	github.com/andybalholm/brotli v1.0.6 // indirect
	github.com/klauspost/compress v1.17.4 // indirect
	golang.org/x/sys v0.31.0 // indirect
)
