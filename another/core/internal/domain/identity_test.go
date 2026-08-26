package domain

import (
	"bytes"
	"crypto/ed25519"
	"testing"
)

func TestHybridIdentitySignVerify(t *testing.T) {
	id, err := GenerateDeviceIdentity()
	if err != nil {
		t.Fatalf("GenerateDeviceIdentity: %v", err)
	}
	if !id.HasMLDSA() {
		t.Fatal("expected ML-DSA key")
	}
	msg := []byte("nonce-ts-payload")
	if !ed25519.Verify(id.PublicKey, msg, id.Sign(msg)) {
		t.Fatal("ed25519 verify failed")
	}
	sig, err := id.SignMLDSA(msg)
	if err != nil {
		t.Fatalf("SignMLDSA: %v", err)
	}
	if !VerifyMLDSA(id.MLDSAPublicKeyHex(), msg, sig) {
		t.Fatal("mldsa65 verify failed")
	}
	sig[0] ^= 0xff
	if VerifyMLDSA(id.MLDSAPublicKeyHex(), msg, sig) {
		t.Fatal("tampered mldsa65 signature must not verify")
	}
}

func TestRestoreThenAttachMLDSA(t *testing.T) {
	id, err := GenerateDeviceIdentity()
	if err != nil {
		t.Fatal(err)
	}
	restored, err := RestoreDeviceIdentity(id.Seed())
	if err != nil {
		t.Fatal(err)
	}
	if restored.HasMLDSA() {
		t.Fatal("ed25519-only restore must not invent ML-DSA")
	}
	if err := restored.WithMLDSASeed(id.MLDSASeed()); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(restored.MLDSPublic, id.MLDSPublic) {
		t.Fatal("mldsa public mismatch after attach")
	}
}
