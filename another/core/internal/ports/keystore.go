package ports

import "github.com/another-vpn/another/core/internal/domain"

// KeyStorePort — driven-порт для хранения приватного ключа устройства.
// Реализации по платформам:
//   - adapters/keystore/file_keystore.go — dev/desktop fallback (файл с
//     правами 0600). ЯВНО НЕ подходит для production на десктопе без доп.
//     защиты (нет привязки к TPM/Secure Enclave) — временный вариант для v1.
//   - TODO v2: keychain_adapter (iOS/macOS, через Keychain Services),
//     android_keystore_adapter (Android Keystore), dpapi_adapter (Windows
//     DPAPI), secret_service_adapter (Linux Secret Service / libsecret).
//     Все требуют cgo или platform-channel вызовов из Flutter — не
//     реализуемо в чистом Go stdlib, поэтому в v1 сознательно вынесено.
type KeyStorePort interface {
	// LoadOrCreateDeviceIdentity возвращает существующую идентичность
	// устройства либо создаёт новую при первом запуске. Без параметров:
	// один слот идентичности на инсталляцию приложения (см. пояснение в
	// domain.DeviceIdentity про то, почему это НЕ индексируется по
	// серверному client_id).
	LoadOrCreateDeviceIdentity() (*domain.DeviceIdentity, error)
}
