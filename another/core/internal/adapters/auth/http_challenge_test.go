package auth

import (
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/another-vpn/another/core/internal/domain"
)

func TestChallengeResponse_Success(t *testing.T) {
	identity, err := domain.GenerateDeviceIdentity()
	if err != nil {
		t.Fatalf("GenerateDeviceIdentity: %v", err)
	}

	const testNonce = "deadbeefcafef00d"
	const testVlessID = "0102030405060708090a0b0c0d0e0f10"

	mux := http.NewServeMux()
	mux.HandleFunc("/nonce", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(nonceResponse{Nonce: testNonce})
	})
	mux.HandleFunc("/auth", func(w http.ResponseWriter, r *http.Request) {
		var req authRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode auth request: %v", err)
		}
		if req.Nonce != testNonce {
			t.Errorf("nonce = %q, want %q", req.Nonce, testNonce)
		}
		if req.ClientID != "test-device" {
			t.Errorf("client_id = %q, want test-device", req.ClientID)
		}

		// проверяем подпись так же, как это делал бы edge worker
		sig, err := hex.DecodeString(req.Signature)
		if err != nil {
			t.Fatalf("decode signature hex: %v", err)
		}
		signPayload := fmt.Sprintf("%s%d", req.Nonce, req.Timestamp)
		if !ed25519.Verify(identity.PublicKey, []byte(signPayload), sig) {
			t.Errorf("signature verification failed")
		}

		json.NewEncoder(w).Encode(authResponse{
			SessionToken: "test-session-token",
			VLESSUserID:  testVlessID,
		})
	})

	server := httptest.NewServer(mux)
	defer server.Close()

	adapter := NewHTTPChallengeAdapter()
	node := domain.NodeDescriptor{Name: "test-node", ControlPlane: server.URL}

	creds, err := adapter.ChallengeResponse(context.Background(), node, "test-device", identity)
	if err != nil {
		t.Fatalf("ChallengeResponse: %v", err)
	}
	if creds.BearerToken != "test-session-token" {
		t.Errorf("BearerToken = %q, want test-session-token", creds.BearerToken)
	}
	wantVless, _ := hex.DecodeString(testVlessID)
	if hex.EncodeToString(creds.VLESSUserID[:]) != hex.EncodeToString(wantVless) {
		t.Errorf("VLESSUserID mismatch: got %x, want %x", creds.VLESSUserID, wantVless)
	}
}

func TestChallengeResponse_MissingControlPlane(t *testing.T) {
	identity, _ := domain.GenerateDeviceIdentity()
	adapter := NewHTTPChallengeAdapter()
	node := domain.NodeDescriptor{Name: "no-control-plane"}

	_, err := adapter.ChallengeResponse(context.Background(), node, "test-device", identity)
	if err == nil {
		t.Fatal("expected error for missing ControlPlane URL")
	}
}
