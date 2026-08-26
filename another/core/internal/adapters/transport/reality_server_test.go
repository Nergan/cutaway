package transport

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha512"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"io"
	"log/slog"
	"math/big"
	"net"
	"strconv"
	"testing"
	"time"

	"github.com/another-vpn/another/core/internal/domain"
)

func TestReplaceX509SignatureHMAC(t *testing.T) {
	authKey := bytesRepeat(0x11, 32)
	cert, err := realityCertificate(authKey, "donor.example")
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := x509.ParseCertificate(cert.Certificate[0])
	if err != nil {
		t.Fatal(err)
	}
	pk, ok := parsed.PublicKey.(ed25519.PublicKey)
	if !ok {
		t.Fatalf("want ed25519, got %T", parsed.PublicKey)
	}
	mac := hmac.New(sha512.New, authKey)
	mac.Write(pk)
	if !hmac.Equal(mac.Sum(nil), parsed.Signature) {
		t.Fatal("cert.Signature is not HMAC-SHA512(authKey, pubkey)")
	}
}

func TestRealityRoundTripEcho(t *testing.T) {
	privHex, pubHex, err := GenerateRealityKeypair()
	if err != nil {
		t.Fatal(err)
	}
	priv, err := ParseRealityPrivateKey(privHex)
	if err != nil {
		t.Fatal(err)
	}
	shortID, _ := hex.DecodeString("aabbccdd")

	echoLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer echoLn.Close()
	go func() {
		for {
			c, err := echoLn.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 16)
				n, _ := c.Read(buf)
				_, _ = c.Write(buf[:n])
			}(c)
		}
	}()

	srvLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer srvLn.Close()
	var logBuf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&logBuf, &slog.HandlerOptions{Level: slog.LevelDebug}))
	var helloDump parsedClientHello
	var authOK bool
	var authSet bool
	var hsErr error
	srv := NewRealityServer(priv, "", [][]byte{shortID}, nil, logger)
	srv.OnHello = func(h parsedClientHello) { helloDump = h }
	srv.OnAuth = func(ok bool) { authOK, authSet = ok, true }
	srv.OnHandshakeErr = func(err error) { hsErr = err }
	go func() { _ = srv.Serve(srvLn) }()

	_, portStr, _ := net.SplitHostPort(srvLn.Addr().String())
	port := mustPort(t, portStr)
	echoHost, echoPortStr, _ := net.SplitHostPort(echoLn.Addr().String())
	echoPort := mustPort(t, echoPortStr)

	node := domain.NodeDescriptor{
		Name:             "vps",
		Host:             "127.0.0.1",
		Port:             port,
		Transport:        domain.TransportVLESSReality,
		SNI:              "localhost",
		RealityPublicKey: pubHex,
		ShortID:          "aabbccdd",
	}
	var uid [16]byte
	uid[0] = 1
	creds := &domain.SessionCredentials{VLESSUserID: uid}

	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	tun, err := NewVLESSRealityTransport().Dial(ctx, node, creds, echoHost, echoPort)
	if err != nil {
		t.Fatalf("reality dial: %v (auth=%v set=%v hsErr=%v sni=%q sid=%d x25519=%d suites=%d hs=%d)\n%s",
			err, authOK, authSet, hsErr, helloDump.SNI, len(helloDump.SessionID), len(helloDump.X25519Pub), len(helloDump.Suites), len(helloDump.Handshake), logBuf.String())
	}
	defer tun.Close()
	if _, err := tun.Write([]byte("ping")); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 8)
	n, err := io.ReadAtLeast(tun, buf[:4], 4)
	if err != nil {
		t.Fatalf("read %d: %v", n, err)
	}
	if string(buf[:4]) != "ping" {
		t.Fatalf("got %q", buf[:n])
	}
}

func TestBadDonorDetect(t *testing.T) {
	if !badDonor("www.google.com:443") {
		t.Fatal("expected warning for google.com")
	}
	if badDonor("www.microsoft.com:443") {
		t.Fatal("microsoft is a typical donor, not banned")
	}
}

func TestProbeDonorLocal(t *testing.T) {
	ln, err := tls.Listen("tcp", "127.0.0.1:0", &tls.Config{Certificates: []tls.Certificate{mustSelfCert(t)}})
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() {
		c, err := ln.Accept()
		if err != nil {
			return
		}
		tc := c.(*tls.Conn)
		_ = tc.Handshake()
		_ = c.Close()
	}()
	info, err := ProbeDonor(ln.Addr().String(), "localhost", 3*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	if info.CommonName == "" && len(info.DNSNames) == 0 {
		t.Fatalf("%+v", info)
	}
}

func mustPort(t *testing.T, s string) uint16 {
	t.Helper()
	p, err := strconv.ParseUint(s, 10, 16)
	if err != nil {
		t.Fatal(err)
	}
	return uint16(p)
}

func mustSelfCert(t *testing.T) tls.Certificate {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	serial, _ := rand.Int(rand.Reader, big.NewInt(1<<62))
	tmpl := &x509.Certificate{
		SerialNumber: serial,
		Subject:      pkix.Name{CommonName: "localhost"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		DNSNames:     []string{"localhost"},
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, pub, priv)
	if err != nil {
		t.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: priv}
}

func bytesRepeat(b byte, n int) []byte {
	out := make([]byte, n)
	for i := range out {
		out[i] = b
	}
	return out
}
