// Package enroll — HTTP-клиент POST /enroll на edge (§7.1).
package enroll

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/another-vpn/another/core/internal/domain"
)

type Client struct {
	HTTP *http.Client
}

func New() *Client {
	return &Client{HTTP: &http.Client{Timeout: 20 * time.Second}}
}

type requestBody struct {
	EnrollmentToken  string `json:"enrollment_token"`
	PublicKey        string `json:"public_key"`
	PublicKeyMLDSA65 string `json:"public_key_mldsa65,omitempty"`
}

type responseBody struct {
	OK       bool            `json:"ok"`
	ClientID string          `json:"client_id"`
	Nodes    json.RawMessage `json:"nodes"`
	Error    string          `json:"error"`
}

func (c *Client) Enroll(ctx context.Context, controlPlane, token, pubHex, pubMLDSAHex string) (string, []domain.NodeDescriptor, error) {
	if c.HTTP == nil {
		c.HTTP = &http.Client{Timeout: 20 * time.Second}
	}
	base := strings.TrimRight(controlPlane, "/")
	payload, err := json.Marshal(requestBody{
		EnrollmentToken:  token,
		PublicKey:        pubHex,
		PublicKeyMLDSA65: pubMLDSAHex,
	})
	if err != nil {
		return "", nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/enroll", bytes.NewReader(payload))
	if err != nil {
		return "", nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return "", nil, fmt.Errorf("enroll: request: %w", err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		return "", nil, fmt.Errorf("enroll: rejected (status %d)", resp.StatusCode)
	}
	var body responseBody
	if err := json.Unmarshal(raw, &body); err != nil {
		return "", nil, fmt.Errorf("enroll: decode: %w", err)
	}
	if body.ClientID == "" {
		return "", nil, fmt.Errorf("enroll: empty client_id")
	}
	nodes, err := domain.ParseNodeList(body.Nodes)
	if err != nil {
		return "", nil, fmt.Errorf("enroll: nodes: %w", err)
	}
	return body.ClientID, nodes, nil
}
