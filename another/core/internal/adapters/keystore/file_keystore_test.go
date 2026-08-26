package keystore

import (
	"bytes"
	"testing"
)

func TestFileKeyStore_CreatesAndPersists(t *testing.T) {
	dir := t.TempDir()
	ks := NewFileKeyStore(dir)

	id1, err := ks.LoadOrCreateDeviceIdentity()
	if err != nil {
		t.Fatalf("first LoadOrCreateDeviceIdentity: %v", err)
	}

	// повторный вызов должен вернуть ТУ ЖЕ идентичность, а не сгенерировать новую
	id2, err := ks.LoadOrCreateDeviceIdentity()
	if err != nil {
		t.Fatalf("second LoadOrCreateDeviceIdentity: %v", err)
	}

	if !bytes.Equal(id1.PublicKey, id2.PublicKey) {
		t.Errorf("public keys differ between calls: %x vs %x", id1.PublicKey, id2.PublicKey)
	}

	sig := id2.Sign([]byte("some data"))
	if len(sig) == 0 {
		t.Error("expected non-empty signature")
	}
}

func TestFileKeyStore_DifferentDirsGetDifferentKeys(t *testing.T) {
	// Разные каталоги = разные "инсталляции" приложения = разные
	// идентичности. Один и тот же каталог всегда даёт один и тот же ключ
	// (см. TestFileKeyStore_CreatesAndPersists) — clientID больше не
	// участвует в выборе слота хранения, см. комментарий в
	// domain.DeviceIdentity про причину.
	dirA := t.TempDir()
	dirB := t.TempDir()
	ksA := NewFileKeyStore(dirA)
	ksB := NewFileKeyStore(dirB)

	idA, _ := ksA.LoadOrCreateDeviceIdentity()
	idB, _ := ksB.LoadOrCreateDeviceIdentity()

	if bytes.Equal(idA.PublicKey, idB.PublicKey) {
		t.Error("expected different keystore directories to yield different keys")
	}
}

func TestFileKeyStore_PublicKeyGeneratedBeforeEnrollmentMatchesLaterUse(t *testing.T) {
	// Регрессионный тест на порядок операций онбординга (§7.1): публичный
	// ключ, полученный ДО того, как известен серверный client_id (напр. для
	// отправки в /enroll), должен быть тем же самым ключом, что
	// используется позже при первом /auth — теперь уже под настоящим
	// client_id. Раньше (v1.0) идентичность была проиндексирована по
	// clientID, и эти два ключа физически не совпадали бы.
	dir := t.TempDir()
	ks := NewFileKeyStore(dir)

	// "До онбординга" — client_id ещё не известен.
	preEnrollIdentity, err := ks.LoadOrCreateDeviceIdentity()
	if err != nil {
		t.Fatalf("pre-enroll LoadOrCreateDeviceIdentity: %v", err)
	}
	publicKeySentToEnroll := preEnrollIdentity.PublicKeyHex()

	// "После онбординга" — используется тот же KeyStore, серверный
	// client_id теперь известен, но НЕ участвует в выборе ключа.
	postEnrollIdentity, err := ks.LoadOrCreateDeviceIdentity()
	if err != nil {
		t.Fatalf("post-enroll LoadOrCreateDeviceIdentity: %v", err)
	}

	if postEnrollIdentity.PublicKeyHex() != publicKeySentToEnroll {
		t.Fatalf("public key mismatch after enrollment: sent %s, later using %s",
			publicKeySentToEnroll, postEnrollIdentity.PublicKeyHex())
	}
}
