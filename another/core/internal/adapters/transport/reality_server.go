package transport

import (
	"bufio"
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"
	"log/slog"
	"net"
	"strings"
	"time"

	"github.com/another-vpn/another/core/internal/adapters/transport/vlessproto"
	"golang.org/x/crypto/chacha20poly1305"
	"golang.org/x/crypto/hkdf"
)

const realityTimestampSkew = 120 * time.Second

var realityBadDonors = []string{"google.com", "www.google.com"}

// RealityServer — origin Reality (протокол XTLS, своя реализация).
// Неаутентифицированный ClientHello уходит на Dest (ответ probe = чужой сайт).
type RealityServer struct {
	PrivateKey     *ecdh.PrivateKey
	ShortIDs       [][]byte
	Dest           string
	ServerNames    []string
	Logger         *slog.Logger
	Dial           func(network, address string, timeout time.Duration) (net.Conn, error)
	OnHello        func(parsedClientHello)
	OnAuth         func(ok bool)
	OnHandshakeErr func(error)
}

func NewRealityServer(priv *ecdh.PrivateKey, dest string, shortIDs [][]byte, names []string, logger *slog.Logger) *RealityServer {
	if logger == nil {
		logger = slog.Default()
	}
	return &RealityServer{
		PrivateKey:  priv,
		ShortIDs:    shortIDs,
		Dest:        dest,
		ServerNames: names,
		Logger:      logger,
		Dial:        func(n, a string, t time.Duration) (net.Conn, error) { return net.DialTimeout(n, a, t) },
	}
}

func GenerateRealityKeypair() (privHex, pubHex string, err error) {
	k, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		return "", "", err
	}
	return hex.EncodeToString(k.Bytes()), hex.EncodeToString(k.PublicKey().Bytes()), nil
}

func ParseRealityPrivateKey(hexKey string) (*ecdh.PrivateKey, error) {
	b, err := hex.DecodeString(strings.TrimSpace(hexKey))
	if err != nil || len(b) != 32 {
		return nil, fmt.Errorf("reality: private key must be 32-byte hex")
	}
	return ecdh.X25519().NewPrivateKey(b)
}

func (s *RealityServer) Serve(ln net.Listener) error {
	for {
		c, err := ln.Accept()
		if err != nil {
			return err
		}
		go s.Handle(c)
	}
}

func (s *RealityServer) Handle(raw net.Conn) {
	defer raw.Close()
	_ = raw.SetDeadline(time.Now().Add(15 * time.Second))
	record, hsBody, err := readTLSRecord(raw)
	if err != nil {
		s.Logger.Debug("reality: read hello", "err", err)
		return
	}
	hello, err := parseClientHello(hsBody)
	if err != nil {
		s.Logger.Debug("reality: parse hello", "err", err)
		s.fallback(raw, record)
		return
	}
	if s.OnHello != nil {
		s.OnHello(hello)
	}
	authKey, ok := s.authenticate(hello)
	if s.OnAuth != nil {
		s.OnAuth(ok)
	}
	if !ok {
		s.Logger.Debug("reality: not a Reality client, fallback", "sni", hello.SNI, "sid", len(hello.SessionID), "x25519", len(hello.X25519Pub))
		s.fallback(raw, record)
		return
	}
	cert, err := realityCertificate(authKey, hello.SNI)
	if err != nil {
		s.Logger.Warn("reality: cert", "err", err)
		return
	}
	cfg := &tls.Config{
		MinVersion:       tls.VersionTLS13,
		MaxVersion:       tls.VersionTLS13,
		Certificates:     []tls.Certificate{cert},
		NextProtos:       []string{"h2", "http/1.1"},
		CurvePreferences: []tls.CurveID{tls.X25519},
	}
	tlsConn := tls.Server(&prefixConn{Conn: raw, prefix: record}, cfg)
	if err := tlsConn.Handshake(); err != nil {
		s.Logger.Debug("reality: handshake", "err", err)
		if s.OnHandshakeErr != nil {
			s.OnHandshakeErr(err)
		}
		return
	}
	_ = raw.SetDeadline(time.Time{})
	s.proxyVLESS(tlsConn)
}

func (s *RealityServer) authenticate(hello parsedClientHello) ([]byte, bool) {
	if len(hello.SessionID) != 32 || len(hello.X25519Pub) != 32 || s.PrivateKey == nil {
		return nil, false
	}
	if len(s.ServerNames) > 0 && !nameAllowed(hello.SNI, s.ServerNames) {
		return nil, false
	}
	peer, err := ecdh.X25519().NewPublicKey(hello.X25519Pub)
	if err != nil {
		return nil, false
	}
	shared, err := s.PrivateKey.ECDH(peer)
	if err != nil {
		return nil, false
	}
	authKey := make([]byte, 32)
	if _, err := io.ReadFull(hkdf.New(sha256.New, shared, hello.Random[:20], []byte("REALITY")), authKey); err != nil {
		return nil, false
	}
	var aead cipher.AEAD
	if aesgcmPreferred(hello.Suites) {
		block, err := aes.NewCipher(authKey)
		if err != nil {
			return nil, false
		}
		aead, err = cipher.NewGCM(block)
		if err != nil {
			return nil, false
		}
	} else {
		aead, err = chacha20poly1305.New(authKey)
		if err != nil {
			return nil, false
		}
	}
	plain, err := aead.Open(nil, hello.Random[20:], hello.SessionID, aadWithZeroSessionID(hello.Handshake))
	if err != nil || len(plain) < 16 {
		s.Logger.Debug("reality: aead", "err", err)
		return nil, false
	}
	if plain[0] != 0 || plain[1] != 2 || plain[2] != 0 {
		return nil, false
	}
	ts := time.Unix(int64(binary.BigEndian.Uint32(plain[4:8])), 0)
	if d := time.Since(ts); d > realityTimestampSkew || d < -realityTimestampSkew {
		return nil, false
	}
	got := plain[8:16]
	for _, want := range s.ShortIDs {
		w := make([]byte, 8)
		copy(w, want)
		if subtle.ConstantTimeCompare(got, w) == 1 {
			return authKey, true
		}
	}
	if len(s.ShortIDs) == 0 {
		var zeros [8]byte
		if subtle.ConstantTimeCompare(got, zeros[:]) == 1 {
			return authKey, true
		}
	}
	return nil, false
}

func (s *RealityServer) fallback(client net.Conn, helloRecord []byte) {
	if s.Dest == "" {
		return
	}
	if badDonor(s.Dest) {
		s.Logger.Warn("reality: dest похож на запрещённый дефолт (google.com) — смените SNI-донора")
	}
	up, err := s.Dial("tcp", s.Dest, 10*time.Second)
	if err != nil {
		s.Logger.Debug("reality: dest dial", "err", err)
		return
	}
	defer up.Close()
	if _, err := up.Write(helloRecord); err != nil {
		return
	}
	errCh := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(up, client)
		errCh <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(client, up)
		errCh <- struct{}{}
	}()
	<-errCh
}

func (s *RealityServer) proxyVLESS(c net.Conn) {
	br := bufio.NewReader(c)
	hdr, err := vlessproto.DecodeRequestHeader(br)
	if err != nil {
		s.Logger.Debug("reality: vless header", "err", err)
		return
	}
	if hdr.Command != vlessproto.CommandTCP {
		return
	}
	up, err := s.Dial("tcp", net.JoinHostPort(hdr.DestHost, fmt.Sprintf("%d", hdr.DestPort)), 10*time.Second)
	if err != nil {
		return
	}
	defer up.Close()
	if err := vlessproto.EncodeResponseHeader(c); err != nil {
		return
	}
	errCh := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(up, br)
		errCh <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(c, up)
		errCh <- struct{}{}
	}()
	<-errCh
}

type prefixConn struct {
	net.Conn
	prefix []byte
}

func (c *prefixConn) Read(p []byte) (int, error) {
	if len(c.prefix) > 0 {
		n := copy(p, c.prefix)
		c.prefix = c.prefix[n:]
		return n, nil
	}
	return c.Conn.Read(p)
}

func nameAllowed(sni string, names []string) bool {
	sni = strings.ToLower(strings.TrimSpace(sni))
	for _, n := range names {
		if strings.EqualFold(strings.TrimSpace(n), sni) {
			return true
		}
	}
	return false
}

func badDonor(dest string) bool {
	host, _, err := net.SplitHostPort(dest)
	if err != nil {
		host = dest
	}
	host = strings.ToLower(host)
	for _, b := range realityBadDonors {
		if host == b {
			return true
		}
	}
	return false
}
