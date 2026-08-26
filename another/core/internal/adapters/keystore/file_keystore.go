// Package keystore содержит реализации ports.KeyStorePort.
package keystore

import (
	"crypto/ed25519"
	"fmt"
	"os"
	"path/filepath"

	"github.com/another-vpn/another/core/internal/domain"
)

// FileKeyStore — dev/desktop-реализация ports.KeyStorePort: seed
// Ed25519-ключа хранится в файле с правами 0600 в указанной директории.
// Один каталог (Dir) = один слот идентичности (см. пояснение в
// domain.DeviceIdentity про то, почему это не индексируется по
// клиентскому/серверному ID) — имя файла фиксировано (identity.seed), а не
// параметризовано, чтобы ключ, сгенерированный до онбординга (когда
// серверный client_id ещё не известен), физически совпадал с ключом,
// используемым позже при аутентификации.
//
// ЯВНО НЕ для production на десктопе без дополнительной защиты: файл на
// диске не привязан к TPM/Secure Enclave, при компрометации диска ключ
// компрометируется полностью. Это сознательный компромисс v1 (см. §11
// спецификации и ports/keystore.go) — реальные keychain/keystore/DPAPI
// адаптеры требуют cgo/platform-channel вызовов, которые нельзя
// реализовать в чистом Go stdlib.
type FileKeyStore struct {
	Dir string
}

func NewFileKeyStore(dir string) *FileKeyStore {
	return &FileKeyStore{Dir: dir}
}

func (f *FileKeyStore) seedPath() string {
	return filepath.Join(f.Dir, "identity.seed")
}

func (f *FileKeyStore) mldsaPath() string {
	return filepath.Join(f.Dir, "identity.mldsa65.seed")
}

func (f *FileKeyStore) LoadOrCreateDeviceIdentity() (*domain.DeviceIdentity, error) {
	if err := os.MkdirAll(f.Dir, 0o700); err != nil {
		return nil, fmt.Errorf("file_keystore: create dir: %w", err)
	}

	path := f.seedPath()
	seed, err := os.ReadFile(path)
	if err == nil {
		if len(seed) != ed25519.SeedSize {
			return nil, fmt.Errorf("file_keystore: corrupt seed file %s (len=%d)", path, len(seed))
		}
		id, err := domain.RestoreDeviceIdentity(seed)
		if err != nil {
			return nil, err
		}
		return f.ensureMLDSA(id)
	}
	if !os.IsNotExist(err) {
		return nil, fmt.Errorf("file_keystore: read seed file: %w", err)
	}

	identity, err := domain.GenerateDeviceIdentity()
	if err != nil {
		return nil, fmt.Errorf("file_keystore: generate identity: %w", err)
	}
	if err := os.WriteFile(path, identity.Seed(), 0o600); err != nil {
		return nil, fmt.Errorf("file_keystore: write seed file: %w", err)
	}
	if err := os.WriteFile(f.mldsaPath(), identity.MLDSASeed(), 0o600); err != nil {
		return nil, fmt.Errorf("file_keystore: write mldsa seed: %w", err)
	}
	return identity, nil
}

func (f *FileKeyStore) ensureMLDSA(id *domain.DeviceIdentity) (*domain.DeviceIdentity, error) {
	raw, err := os.ReadFile(f.mldsaPath())
	if err == nil {
		if err := id.WithMLDSASeed(raw); err != nil {
			return nil, fmt.Errorf("file_keystore: restore mldsa: %w", err)
		}
		return id, nil
	}
	if !os.IsNotExist(err) {
		return nil, fmt.Errorf("file_keystore: read mldsa seed: %w", err)
	}
	fresh, err := domain.GenerateDeviceIdentity()
	if err != nil {
		return nil, err
	}
	if err := id.WithMLDSASeed(fresh.MLDSASeed()); err != nil {
		return nil, err
	}
	if err := os.WriteFile(f.mldsaPath(), id.MLDSASeed(), 0o600); err != nil {
		return nil, err
	}
	return id, nil
}
