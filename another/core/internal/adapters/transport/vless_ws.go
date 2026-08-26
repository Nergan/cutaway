package transport

import (
	"bufio"
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"time"

	"github.com/another-vpn/another/core/internal/adapters/transport/vlessproto"
	"github.com/another-vpn/another/core/internal/adapters/transport/wsproto"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// dialTimeout ограничивает время установления TCP+TLS+WS-рукопожатия до узла
// (не путать с таймаутом самой сессии — после рукопожатия соединение может
// жить сколь угодно долго).
const dialTimeout = 10 * time.Second

// VLESSWebSocketTransport — реализация OutboundTransportPort для Tier1
// (см. §9.1 спецификации): VLESS поверх WebSocket поверх TLS, точка
// терминации TLS — Cloudflare Worker/Render. Использует crypto/tls
// стандартной библиотеки; полноценная uTLS-мимикрия под конкретный браузер —
// задокументированное развитие (см. vless_reality.go про то, почему это
// вообще отдельная история для Reality, и README.md корня core/ — раздел
// "Что дальше").
type VLESSWebSocketTransport struct {
	// TLSConfig позволяет переопределить конфигурацию TLS в тестах
	// (напр. InsecureSkipVerify против локального тестового сервера).
	// В production передаётся nil — тогда используется безопасная
	// конфигурация по умолчанию (проверка сертификата по SNI узла).
	TLSConfig *tls.Config
}

func NewVLESSWebSocketTransport() *VLESSWebSocketTransport {
	return &VLESSWebSocketTransport{}
}

func (t *VLESSWebSocketTransport) Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (ports.Tunnel, error) {
	if creds == nil {
		return nil, fmt.Errorf("vless_ws: nil session credentials")
	}

	dialer := &net.Dialer{Timeout: dialTimeout}
	addr := net.JoinHostPort(node.Host, fmt.Sprintf("%d", node.Port))

	rawConn, err := dialer.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("vless_ws: dial %s: %w", addr, err)
	}

	tlsConfig := t.TLSConfig
	if tlsConfig == nil {
		sni := node.SNI
		if sni == "" {
			sni = node.Host
		}
		tlsConfig = &tls.Config{ServerName: sni, MinVersion: tls.VersionTLS12}
	}
	tlsConn := tls.Client(rawConn, tlsConfig)
	if err := tlsConn.HandshakeContext(ctx); err != nil {
		rawConn.Close()
		return nil, fmt.Errorf("vless_ws: tls handshake: %w", err)
	}

	path := node.Path
	if path == "" {
		path = "/"
	}
	headers := map[string]string{
		"Authorization": "Bearer " + creds.BearerToken,
	}
	wsConn, err := wsproto.Handshake(tlsConn, path, node.Host, headers)
	if err != nil {
		tlsConn.Close()
		return nil, fmt.Errorf("vless_ws: websocket handshake: %w", err)
	}

	if err := vlessproto.EncodeRequestHeader(wsConn, creds.VLESSUserID, vlessproto.CommandTCP, destHost, destPort); err != nil {
		wsConn.Close()
		return nil, fmt.Errorf("vless_ws: encode vless header: %w", err)
	}

	br := bufio.NewReader(wsConn)
	if err := vlessproto.DecodeResponseHeader(br); err != nil {
		wsConn.Close()
		return nil, fmt.Errorf("vless_ws: decode vless response: %w", err)
	}

	return &vlessTunnel{ws: wsConn, br: br}, nil
}

// vlessTunnel оборачивает wsproto.Conn так, чтобы первые байты после
// VLESS-заголовка ответа читались из уже заполненного bufio.Reader
// (DecodeResponseHeader мог прочитать больше байт, чем сам заголовок,
// если сервер прислал заголовок и начало полезной нагрузки одним фреймом).
type vlessTunnel struct {
	ws *wsproto.Conn
	br *bufio.Reader
}

func (v *vlessTunnel) Read(p []byte) (int, error)  { return v.br.Read(p) }
func (v *vlessTunnel) Write(p []byte) (int, error) { return v.ws.Write(p) }
func (v *vlessTunnel) Close() error                { return v.ws.Close() }
