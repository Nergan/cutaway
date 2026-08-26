package transport

import (
	"bufio"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/sha512"
	"crypto/x509"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"strings"
	"time"

	"github.com/another-vpn/another/core/internal/adapters/transport/vlessproto"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
	utls "github.com/refraction-networking/utls"
	"golang.org/x/crypto/chacha20poly1305"
	"golang.org/x/crypto/hkdf"
)

// VLESSRealityTransport — клиент Reality (публичный протокол XTLS):
// uTLS Chrome fingerprint + SessionId с AEAD(authkey). Код свой, по
// описанию протокола. Сервер в проде — фаза 4 (VPS); клиент уже умеет
// говорить с совместимым Reality-узлом, в том числе с cmd/reality-origin.
type VLESSRealityTransport struct{}

func NewVLESSRealityTransport() *VLESSRealityTransport { return &VLESSRealityTransport{} }

func (t *VLESSRealityTransport) Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (ports.Tunnel, error) {
	if creds == nil {
		return nil, fmt.Errorf("vless_reality: nil credentials")
	}
	pub, err := parseRealityPub(node.RealityPublicKey)
	if err != nil {
		return nil, fmt.Errorf("vless_reality: public key: %w", err)
	}
	shortID, err := parseShortID(node.ShortID)
	if err != nil {
		return nil, err
	}
	sni := node.SNI
	if sni == "" {
		sni = node.Host
	}

	d := &net.Dialer{Timeout: 10 * time.Second}
	addr := net.JoinHostPort(node.Host, fmt.Sprintf("%d", node.Port))
	raw, err := d.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("vless_reality: dial: %w", err)
	}

	uconn, verified, err := realityHandshake(ctx, raw, sni, pub, shortID)
	if err != nil {
		raw.Close()
		return nil, err
	}
	if !verified {
		uconn.Close()
		return nil, fmt.Errorf("vless_reality: сервер не подтвердил Reality (чужой TLS / probe dest)")
	}

	if err := vlessproto.EncodeRequestHeader(uconn, creds.VLESSUserID, vlessproto.CommandTCP, destHost, destPort); err != nil {
		uconn.Close()
		return nil, fmt.Errorf("vless_reality: vless header: %w", err)
	}
	br := bufio.NewReader(uconn)
	if err := vlessproto.DecodeResponseHeader(br); err != nil {
		uconn.Close()
		return nil, fmt.Errorf("vless_reality: vless response: %w", err)
	}
	return &realityTunnel{c: uconn, br: br}, nil
}

type realityTunnel struct {
	c  net.Conn
	br *bufio.Reader
}

func (t *realityTunnel) Read(p []byte) (int, error)  { return t.br.Read(p) }
func (t *realityTunnel) Write(p []byte) (int, error) { return t.c.Write(p) }
func (t *realityTunnel) Close() error                { return t.c.Close() }

func parseRealityPub(s string) ([]byte, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil, fmt.Errorf("empty")
	}
	b, err := hex.DecodeString(s)
	if err != nil || len(b) != 32 {
		return nil, fmt.Errorf("want 32-byte hex X25519 public key")
	}
	return b, nil
}

func parseShortID(s string) ([]byte, error) {
	s = strings.TrimSpace(s)
	out := make([]byte, 8)
	if s == "" {
		return out, nil
	}
	b, err := hex.DecodeString(s)
	if err != nil || len(b) > 8 {
		return nil, fmt.Errorf("vless_reality: short_id hex 0-8 bytes")
	}
	copy(out, b)
	return out, nil
}

func realityHandshake(ctx context.Context, raw net.Conn, sni string, serverPub, shortID []byte) (*utls.UConn, bool, error) {
	verified := false
	var authKey []byte
	cfg := &utls.Config{
		ServerName:             sni,
		InsecureSkipVerify:     true,
		SessionTicketsDisabled: true,
		VerifyPeerCertificate: func(rawCerts [][]byte, _ [][]*x509.Certificate) error {
			if len(rawCerts) == 0 || len(authKey) == 0 {
				return nil
			}
			cert, err := x509.ParseCertificate(rawCerts[0])
			if err != nil {
				return err
			}
			pk, ok := cert.PublicKey.(ed25519.PublicKey)
			if !ok {
				return nil
			}
			mac := hmac.New(sha512.New, authKey)
			mac.Write(pk)
			if hmac.Equal(mac.Sum(nil), cert.Signature) {
				verified = true
			}
			return nil
		},
	}
	uc := utls.UClient(raw, cfg, utls.HelloChrome_Auto)

	if err := uc.BuildHandshakeState(); err != nil {
		return nil, false, err
	}
	// Chrome 133 не шлёт Ed25519 в signature_algorithms. Reality-сертификат
	// всегда Ed25519 (HMAC поверх pubkey) — без схемы в ClientHello
	// crypto/tls.Server отвечает handshake_failure. Клиент uTLS проверяет
	// схему по своему списку, не по объявленному, так что Xray-узлы и так
	// принимаются; объявление нужно нашему origin на стандартной библиотеке.
	if err := offerEd25519(uc); err != nil {
		return nil, false, err
	}
	hello := uc.HandshakeState.Hello
	hello.SessionId = make([]byte, 32)
	if len(hello.Raw) < 71 {
		return nil, false, fmt.Errorf("vless_reality: ClientHello too short")
	}
	copy(hello.Raw[39:], hello.SessionId)
	hello.SessionId[0], hello.SessionId[1], hello.SessionId[2] = 0, 2, 0
	binary.BigEndian.PutUint32(hello.SessionId[4:8], uint32(time.Now().Unix()))
	copy(hello.SessionId[8:], shortID)

	pub, err := ecdh.X25519().NewPublicKey(serverPub)
	if err != nil {
		return nil, false, err
	}
	ksk := uc.HandshakeState.State13.KeyShareKeys
	if ksk == nil {
		return nil, false, fmt.Errorf("vless_reality: no key shares")
	}
	priv := ksk.Ecdhe
	if priv == nil {
		priv = ksk.MlkemEcdhe
	}
	if priv == nil {
		return nil, false, fmt.Errorf("vless_reality: no X25519 share in fingerprint")
	}
	shared, err := priv.ECDH(pub)
	if err != nil {
		return nil, false, err
	}
	authKey = make([]byte, 32)
	if _, err := io.ReadFull(hkdf.New(sha256.New, shared, hello.Random[:20], []byte("REALITY")), authKey); err != nil {
		return nil, false, err
	}

	var aead cipher.AEAD
	if aesgcmPreferred(hello.CipherSuites) {
		block, err := aes.NewCipher(authKey)
		if err != nil {
			return nil, false, err
		}
		aead, err = cipher.NewGCM(block)
		if err != nil {
			return nil, false, err
		}
	} else {
		aead, err = chacha20poly1305.New(authKey)
		if err != nil {
			return nil, false, err
		}
	}
	aead.Seal(hello.SessionId[:0], hello.Random[20:], hello.SessionId[:16], hello.Raw)
	copy(hello.Raw[39:], hello.SessionId)

	if err := uc.HandshakeContext(ctx); err != nil {
		return nil, false, fmt.Errorf("vless_reality: handshake: %w", err)
	}
	return uc, verified, nil
}

func offerEd25519(uc *utls.UConn) error {
	found := false
	for _, ext := range uc.Extensions {
		sa, ok := ext.(*utls.SignatureAlgorithmsExtension)
		if !ok {
			continue
		}
		for _, alg := range sa.SupportedSignatureAlgorithms {
			if alg == utls.Ed25519 {
				return nil
			}
		}
		sa.SupportedSignatureAlgorithms = append(append([]utls.SignatureScheme(nil), sa.SupportedSignatureAlgorithms...), utls.Ed25519)
		found = true
	}
	if !found {
		return fmt.Errorf("vless_reality: no signature_algorithms in fingerprint")
	}
	return uc.MarshalClientHello()
}

func aesgcmPreferred(suites []uint16) bool {
	for _, s := range suites {
		if s == utls.TLS_AES_128_GCM_SHA256 || s == utls.TLS_AES_256_GCM_SHA384 {
			return true
		}
	}
	return false
}
