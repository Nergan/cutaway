// Package config загружает конфигурацию ядра из переменных окружения.
package config

import (
	"bufio"
	"os"
	"strconv"
	"strings"
)

// Config — параметры composition root'а (cmd/desktop, cmd/mobilelib).
type Config struct {
	// ClientID — человекочитаемая метка устройства (не секрет), см.
	// domain.DeviceIdentity.
	ClientID string

	// KeyStoreDir — где хранить seed Ed25519-ключа (см. keystore.FileKeyStore).
	KeyStoreDir string

	// ControlPlaneURL — базовый URL edge control-plane (Cloudflare Worker),
	// см. §7 спецификации. Пример: https://cf-worker.another.example.
	ControlPlaneURL string

	// LocalAPIAddr — на каком адресе cmd/desktop поднимает локальный HTTP API
	// для GUI (см. §5.2: loopback-адрес вместо unix socket/named pipe, чтобы
	// оставаться кроссплатформенным без внешних зависимостей в v1).
	LocalAPIAddr string
}

const (
	envClientID        = "ANOTHER_CLIENT_ID"
	envKeyStoreDir     = "ANOTHER_KEYSTORE_DIR"
	envControlPlaneURL = "ANOTHER_CONTROL_PLANE_URL"
	envLocalAPIAddr    = "ANOTHER_LOCAL_API_ADDR"
)

// Load читает конфигурацию из переменных окружения процесса. Перед вызовом
// Load вызывающая сторона (main.go) может вызвать LoadDotEnv, чтобы
// предварительно подмешать значения из .env-файла (только для локальной
// разработки — см. предупреждение в LoadDotEnv).
func Load() Config {
	return Config{
		ClientID:        getEnvOrDefault(envClientID, "dev-device"),
		KeyStoreDir:     getEnvOrDefault(envKeyStoreDir, defaultKeyStoreDir()),
		ControlPlaneURL: getEnvOrDefault(envControlPlaneURL, "http://127.0.0.1:8787"),
		LocalAPIAddr:    getEnvOrDefault(envLocalAPIAddr, "127.0.0.1:47821"),
	}
}

func getEnvOrDefault(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

func defaultKeyStoreDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".another/keystore"
	}
	return home + string(os.PathSeparator) + ".another" + string(os.PathSeparator) + "keystore"
}

// LoadDotEnv — намеренно простой парсер файла вида KEY=VALUE (по строке),
// без поддержки экранирования/многострочных значений. ТОЛЬКО для локальной
// разработки: в production переменные окружения должны задаваться реальным
// оркестратором (systemd/docker/CI secrets), а не читаться из файла на
// диске — см. предупреждение в корневом .env.example.
//
// Существующие переменные окружения процесса НЕ перезаписываются —
// .env задаёт только значения по умолчанию для локального запуска.
func LoadDotEnv(path string) error {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // .env отсутствует — не ошибка, просто используем окружение/дефолты
		}
		return err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		idx := strings.IndexByte(line, '=')
		if idx <= 0 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		value := strings.TrimSpace(line[idx+1:])
		value = strings.Trim(value, `"'`)
		if _, exists := os.LookupEnv(key); !exists {
			os.Setenv(key, value)
		}
	}
	return scanner.Err()
}

// ParseRateLimit — вспомогательная функция для парсинга значений вида
// "1250000" (байт/сек) из окружения в composition root, без внешних
// зависимостей на flag-парсинг библиотеки.
func ParseRateLimit(raw string, def float64) float64 {
	if raw == "" {
		return def
	}
	v, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return def
	}
	return v
}
