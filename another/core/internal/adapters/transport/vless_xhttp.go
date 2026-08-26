package transport

import (
	"bufio"
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/another-vpn/another/core/internal/adapters/transport/vlessproto"
	"github.com/another-vpn/another/core/internal/adapters/transport/xhttp"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// VLESSXHTTPTransport — split HTTP (stream-up): длинный POST = uplink,
// длинный GET = downlink. Свой фрейминг, не копия xray. Path по умолчанию /xhttp.
type VLESSXHTTPTransport struct {
	TLSConfig *tls.Config
}

func NewVLESSXHTTPTransport() *VLESSXHTTPTransport { return &VLESSXHTTPTransport{} }

func (t *VLESSXHTTPTransport) Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (ports.Tunnel, error) {
	if creds == nil {
		return nil, fmt.Errorf("vless_xhttp: nil credentials")
	}
	sid := xhttp.NewSessionID()
	path := node.Path
	if path == "" {
		path = xhttp.DefaultPath
	}
	scheme := "https"
	if node.Port == 80 {
		scheme = "http"
	}
	hostport := net.JoinHostPort(node.Host, fmt.Sprintf("%d", node.Port))
	base := scheme + "://" + hostport
	upURL := xhttp.JoinURL(base, path, sid)
	downURL := upURL

	tlsCfg := t.TLSConfig
	if tlsCfg == nil {
		sni := node.SNI
		if sni == "" {
			sni = node.Host
		}
		tlsCfg = &tls.Config{ServerName: sni, NextProtos: []string{"h2", "http/1.1"}, MinVersion: tls.VersionTLS12}
	}

	client := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig:     tlsCfg,
			ForceAttemptHTTP2:   true,
			IdleConnTimeout:     90 * time.Second,
			TLSHandshakeTimeout: 10 * time.Second,
			DialContext:         (&net.Dialer{Timeout: 10 * time.Second}).DialContext,
		},
	}

	upReader, upWriter := io.Pipe()
	upReq, err := http.NewRequestWithContext(ctx, http.MethodPost, upURL, upReader)
	if err != nil {
		return nil, err
	}
	xhttp.CopyBrowserHeaders(upReq.Header)
	upReq.Header.Set("Content-Type", "application/octet-stream")
	if creds.BearerToken != "" {
		upReq.Header.Set("Authorization", "Bearer "+creds.BearerToken)
	}

	downReq, err := http.NewRequestWithContext(ctx, http.MethodGet, downURL, nil)
	if err != nil {
		return nil, err
	}
	xhttp.CopyBrowserHeaders(downReq.Header)
	if creds.BearerToken != "" {
		downReq.Header.Set("Authorization", "Bearer "+creds.BearerToken)
	}

	downResp, err := client.Do(downReq)
	if err != nil {
		return nil, fmt.Errorf("vless_xhttp: GET: %w", err)
	}
	if downResp.StatusCode != http.StatusOK {
		_ = downResp.Body.Close()
		return nil, fmt.Errorf("vless_xhttp: GET status %d", downResp.StatusCode)
	}

	go func() {
		resp, err := client.Do(upReq)
		if err != nil {
			_ = upWriter.CloseWithError(err)
			return
		}
		io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

	if err := vlessproto.EncodeRequestHeader(upWriter, creds.VLESSUserID, vlessproto.CommandTCP, destHost, destPort); err != nil {
		_ = downResp.Body.Close()
		_ = upWriter.Close()
		return nil, fmt.Errorf("vless_xhttp: vless header: %w", err)
	}
	br := bufio.NewReader(downResp.Body)
	if err := vlessproto.DecodeResponseHeader(br); err != nil {
		_ = downResp.Body.Close()
		_ = upWriter.Close()
		return nil, fmt.Errorf("vless_xhttp: vless response: %w", err)
	}

	return &xhttpTunnel{up: upWriter, down: br, body: downResp.Body, rawUp: upReader}, nil
}

type xhttpTunnel struct {
	up    *io.PipeWriter
	down  *bufio.Reader
	body  io.Closer
	rawUp *io.PipeReader
	once  sync.Once
}

func (t *xhttpTunnel) Read(p []byte) (int, error)  { return t.down.Read(p) }
func (t *xhttpTunnel) Write(p []byte) (int, error) { return t.up.Write(p) }
func (t *xhttpTunnel) Close() error {
	var err error
	t.once.Do(func() {
		_ = t.up.Close()
		err = t.body.Close()
	})
	return err
}
