// Package domain содержит бизнес-логику ядра, не зависящую ни от одного
// внешнего фреймворка, ОС-специфичного API или сетевой библиотеки.
// Это центр гексагональной архитектуры: порты (internal/ports) описывают,
// что домену нужно от внешнего мира, адаптеры (internal/adapters) это
// реализуют, а domain ничего не знает ни про один конкретный адаптер.
//
// Исключение фазы 2: ML-DSA-65 (FIPS 204) через circl — это та же роль,
// что и crypto/ed25519 из stdlib: чистая криптография идентичности,
// не «адаптер ОС». См. docs/adr/0006-pq-hybrid-identity.md.
package domain

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"fmt"

	"github.com/cloudflare/circl/sign/mldsa/mldsa65"
)

// DeviceIdentity — криптографическая идентичность устройства.
//
// В черновике спецификации идентификатором устройства был MAC-адрес
// ("HWID"). Это не работает: с ~2020 года iOS и Android не отдают
// приложениям реальный MAC Wi-Fi (рандомизация на уровне ОС), а сам MAC
// тривиально подделывается. Здесь идентичность устройства — гибрид
// Ed25519 + ML-DSA-65, сгенерированный на самом устройстве. Приватное
// никогда не покидает KeyStorePort. Публичные ключи — идентификатор в
// модели TOFU (Trust On First Use).
//
// ВАЖНО: структура намеренно не содержит серверного client_id. Причина —
// порядок операций при онбординге (§7.1 спецификации): устройство должно
// сгенерировать публичные ключи и отправить их в /enroll ДО того, как
// сервер вернёт ему присвоенный client_id. Поэтому идентичность привязана к
// ОДНОМУ фиксированному локальному слоту на инсталляцию приложения.
type DeviceIdentity struct {
	PublicKey  ed25519.PublicKey
	privateKey ed25519.PrivateKey
	MLDSPublic []byte
	mldsaSeed  []byte
}

// GenerateDeviceIdentity создаёт новую гибридную пару ключей.
func GenerateDeviceIdentity() (*DeviceIdentity, error) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, fmt.Errorf("domain: generate ed25519 key: %w", err)
	}
	var seed [mldsa65.SeedSize]byte
	if _, err := rand.Read(seed[:]); err != nil {
		return nil, fmt.Errorf("domain: generate mldsa65 seed: %w", err)
	}
	id := &DeviceIdentity{
		PublicKey:  pub,
		privateKey: priv,
	}
	if err := id.attachMLDSA(seed[:]); err != nil {
		return nil, err
	}
	return id, nil
}

// RestoreDeviceIdentity восстанавливает Ed25519 из 32-байтового seed.
// ML-DSA нужно навесить отдельно через WithMLDSASeed (файл
// identity.mldsa65.seed) — так старые установки без PQ-файла остаются
// читаемыми и дописывают ML-DSA при первом Load.
func RestoreDeviceIdentity(seed []byte) (*DeviceIdentity, error) {
	if len(seed) != ed25519.SeedSize {
		return nil, fmt.Errorf("domain: invalid seed length %d, want %d", len(seed), ed25519.SeedSize)
	}
	priv := ed25519.NewKeyFromSeed(seed)
	pub := priv.Public().(ed25519.PublicKey)
	return &DeviceIdentity{
		PublicKey:  pub,
		privateKey: priv,
	}, nil
}

// WithMLDSASeed дописывает ML-DSA-65 к уже восстановленной Ed25519-идентичности.
func (d *DeviceIdentity) WithMLDSASeed(seed []byte) error {
	return d.attachMLDSA(seed)
}

func (d *DeviceIdentity) attachMLDSA(seed []byte) error {
	if len(seed) != mldsa65.SeedSize {
		return fmt.Errorf("domain: invalid mldsa65 seed length %d, want %d", len(seed), mldsa65.SeedSize)
	}
	var s [mldsa65.SeedSize]byte
	copy(s[:], seed)
	pk, _ := mldsa65.NewKeyFromSeed(&s)
	d.MLDSPublic = pk.Bytes()
	d.mldsaSeed = append([]byte(nil), seed...)
	return nil
}

// Seed возвращает 32-байтовый Ed25519 seed для KeyStorePort.
func (d *DeviceIdentity) Seed() []byte {
	return d.privateKey.Seed()
}

// MLDSASeed возвращает 32-байтовый seed ML-DSA-65 (копия).
func (d *DeviceIdentity) MLDSASeed() []byte {
	return append([]byte(nil), d.mldsaSeed...)
}

// HasMLDSA сообщает, навешан ли постквантовый ключ.
func (d *DeviceIdentity) HasMLDSA() bool {
	return len(d.mldsaSeed) == mldsa65.SeedSize
}

// PublicKeyHex — Ed25519 public в hex (`clients.public_key`).
func (d *DeviceIdentity) PublicKeyHex() string {
	return hex.EncodeToString(d.PublicKey)
}

// MLDSAPublicKeyHex — ML-DSA-65 public в hex (`clients.public_key_mldsa65`).
func (d *DeviceIdentity) MLDSAPublicKeyHex() string {
	return hex.EncodeToString(d.MLDSPublic)
}

// Sign — Ed25519(nonce ⧺ timestamp) для Worker WebCrypto.
func (d *DeviceIdentity) Sign(data []byte) []byte {
	return ed25519.Sign(d.privateKey, data)
}

// SignMLDSA — подпись ML-DSA-65 того же сообщения. Worker может её
// игнорировать, пока workerd не стабилизирует PQ; origin проверяет оба.
func (d *DeviceIdentity) SignMLDSA(data []byte) ([]byte, error) {
	if !d.HasMLDSA() {
		return nil, fmt.Errorf("domain: mldsa65 key missing")
	}
	var s [mldsa65.SeedSize]byte
	copy(s[:], d.mldsaSeed)
	_, sk := mldsa65.NewKeyFromSeed(&s)
	sig := make([]byte, mldsa65.SignatureSize)
	if err := mldsa65.SignTo(sk, data, nil, false, sig); err != nil {
		return nil, fmt.Errorf("domain: mldsa65 sign: %w", err)
	}
	return sig, nil
}

// VerifyMLDSA проверяет подпись ML-DSA-65 (тесты и origin).
func VerifyMLDSA(publicKeyHex string, msg, sig []byte) bool {
	raw, err := hex.DecodeString(publicKeyHex)
	if err != nil {
		return false
	}
	var pk mldsa65.PublicKey
	if err := pk.UnmarshalBinary(raw); err != nil {
		return false
	}
	return mldsa65.Verify(&pk, msg, nil, sig)
}
