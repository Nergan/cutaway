package probe

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"sync"
	"time"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// TCPProber меряет TCP (+TLS на 443) до node.Host:Port.
type TCPProber struct {
	Timeout time.Duration
}

func NewTCPProber() *TCPProber {
	return &TCPProber{Timeout: 3 * time.Second}
}

func (p *TCPProber) Probe(ctx context.Context, nodes []domain.NodeDescriptor) []domain.ProbeResult {
	out := make([]domain.ProbeResult, len(nodes))
	var wg sync.WaitGroup
	for i, n := range nodes {
		wg.Add(1)
		go func(i int, n domain.NodeDescriptor) {
			defer wg.Done()
			out[i] = p.one(ctx, n)
		}(i, n)
	}
	wg.Wait()
	return out
}

func (p *TCPProber) one(ctx context.Context, n domain.NodeDescriptor) domain.ProbeResult {
	res := domain.ProbeResult{Name: n.Name}
	d := &net.Dialer{Timeout: p.Timeout}
	addr := net.JoinHostPort(n.Host, fmt.Sprintf("%d", n.Port))
	start := time.Now()
	c, err := d.DialContext(ctx, "tcp", addr)
	if err != nil {
		res.Err = err.Error()
		return res
	}
	if n.Port == 443 {
		sni := n.SNI
		if sni == "" {
			sni = n.Host
		}
		tc := tls.Client(c, &tls.Config{ServerName: sni, InsecureSkipVerify: true, MinVersion: tls.VersionTLS12})
		if err := tc.HandshakeContext(ctx); err != nil {
			_ = c.Close()
			res.Err = err.Error()
			return res
		}
		_ = tc.Close()
	} else {
		_ = c.Close()
	}
	res.OK = true
	res.RTT = time.Since(start).Nanoseconds()
	return res
}

var _ ports.ProbePort = (*TCPProber)(nil)
