// Package auth содержит реализации ports.AuthPort.
package auth

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/another-vpn/another/core/internal/domain"
)

// HTTPChallengeAdapter реализует ports.AuthPort через HTTP-эндпоинты
// control-plane, описанные в §7.2 спецификации: GET /nonce → подпись
// Ed25519(nonce ⧺ timestamp) → POST /auth → session credentials.
type HTTPChallengeAdapter struct {
	HTTPClient *http.Client
}

func NewHTTPChallengeAdapter() *HTTPChallengeAdapter {
	return &HTTPChallengeAdapter{
		HTTPClient: &http.Client{Timeout: 10 * time.Second},
	}
}

type nonceResponse struct {
	Nonce string `json:"nonce"`
}

type authRequest struct {
	ClientID         string `json:"client_id"`
	Signature        string `json:"signature"` // hex Ed25519
	SignatureMLDSA65 string `json:"signature_mldsa65,omitempty"`
	PublicKeyMLDSA65 string `json:"public_key_mldsa65,omitempty"`
	Timestamp        int64  `json:"timestamp"`
	Nonce            string `json:"nonce"`
}

type authResponse struct {
	SessionToken string `json:"session_token"`
	VLESSUserID  string `json:"vless_user_id"` // hex, 16 байт
}

func (a *HTTPChallengeAdapter) ChallengeResponse(ctx context.Context, node domain.NodeDescriptor, clientID string, identity *domain.DeviceIdentity) (*domain.SessionCredentials, error) {
	if node.ControlPlane == "" {
		return nil, fmt.Errorf("http_challenge: node %q has no ControlPlane URL", node.Name)
	}

	nonce, err := a.requestNonce(ctx, node.ControlPlane)
	if err != nil {
		return nil, fmt.Errorf("http_challenge: request nonce: %w", err)
	}

	timestamp := time.Now().Unix()
	signPayload := fmt.Sprintf("%s%d", nonce, timestamp)
	signature := identity.Sign([]byte(signPayload))
	req := authRequest{
		ClientID:  clientID,
		Signature: hex.EncodeToString(signature),
		Timestamp: timestamp,
		Nonce:     nonce,
	}
	if identity.HasMLDSA() {
		mldsaSig, err := identity.SignMLDSA([]byte(signPayload))
		if err != nil {
			return nil, fmt.Errorf("http_challenge: mldsa sign: %w", err)
		}
		req.SignatureMLDSA65 = hex.EncodeToString(mldsaSig)
		req.PublicKeyMLDSA65 = identity.MLDSAPublicKeyHex()
	}

	resp, err := a.postAuth(ctx, node.ControlPlane, req)
	if err != nil {
		return nil, fmt.Errorf("http_challenge: auth request: %w", err)
	}

	vlessIDBytes, err := hex.DecodeString(resp.VLESSUserID)
	if err != nil || len(vlessIDBytes) != 16 {
		return nil, fmt.Errorf("http_challenge: invalid vless_user_id in response")
	}
	var vlessID [16]byte
	copy(vlessID[:], vlessIDBytes)

	return &domain.SessionCredentials{
		BearerToken: resp.SessionToken,
		VLESSUserID: vlessID,
	}, nil
}

func (a *HTTPChallengeAdapter) requestNonce(ctx context.Context, baseURL string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+"/nonce", nil)
	if err != nil {
		return "", err
	}
	resp, err := a.HTTPClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return "", fmt.Errorf("unexpected status %d: %s", resp.StatusCode, body)
	}

	var nr nonceResponse
	if err := json.NewDecoder(resp.Body).Decode(&nr); err != nil {
		return "", fmt.Errorf("decode nonce response: %w", err)
	}
	return nr.Nonce, nil
}

func (a *HTTPChallengeAdapter) postAuth(ctx context.Context, baseURL string, body authRequest) (*authResponse, error) {
	payload, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/auth", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("unexpected status %d: %s", resp.StatusCode, respBody)
	}

	var ar authResponse
	if err := json.NewDecoder(resp.Body).Decode(&ar); err != nil {
		return nil, fmt.Errorf("decode auth response: %w", err)
	}
	return &ar, nil
}
