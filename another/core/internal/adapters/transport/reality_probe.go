package transport

import (
	"crypto/tls"
	"fmt"
	"net"
	"strings"
	"time"
)

// DonorProbe — результат TLS-проверки SNI-донора (не сканер подсети).
type DonorProbe struct {
	Addr       string
	TLSVersion uint16
	ALPN       string
	CommonName string
	DNSNames   []string
	Issuer     string
	NotAfter   time.Time
	WarnGoogle bool
}

func (p DonorProbe) String() string {
	ver := fmt.Sprintf("0x%x", p.TLSVersion)
	switch p.TLSVersion {
	case tls.VersionTLS13:
		ver = "TLS1.3"
	case tls.VersionTLS12:
		ver = "TLS1.2"
	}
	warn := ""
	if p.WarnGoogle {
		warn = " WARN: google.com как донор на облачной подсети обычно палит Reality"
	}
	return fmt.Sprintf("addr=%s ver=%s alpn=%s cn=%s dns=%s issuer=%s not_after=%s%s",
		p.Addr, ver, p.ALPN, p.CommonName, strings.Join(p.DNSNames, ","), p.Issuer, p.NotAfter.UTC().Format(time.RFC3339), warn)
}

// ProbeDonor делает одно TLS-рукопожатие к кандидату. Полный скан /24 — внешний
// RealiTLScanner (не переписываем).
func ProbeDonor(addr, sni string, timeout time.Duration) (DonorProbe, error) {
	if sni == "" {
		host, _, err := net.SplitHostPort(addr)
		if err == nil {
			sni = host
		} else {
			sni = addr
		}
	}
	cfg := &tls.Config{
		ServerName:         sni,
		InsecureSkipVerify: true,
		NextProtos:         []string{"h2", "http/1.1"},
		MinVersion:         tls.VersionTLS12,
	}
	d := &net.Dialer{Timeout: timeout}
	raw, err := d.Dial("tcp", addr)
	if err != nil {
		return DonorProbe{}, err
	}
	conn := tls.Client(raw, cfg)
	defer conn.Close()
	if err := conn.Handshake(); err != nil {
		return DonorProbe{}, err
	}
	st := conn.ConnectionState()
	out := DonorProbe{Addr: addr, TLSVersion: st.Version, ALPN: st.NegotiatedProtocol, WarnGoogle: badDonor(net.JoinHostPort(sni, "443"))}
	if len(st.PeerCertificates) > 0 {
		c := st.PeerCertificates[0]
		out.CommonName = c.Subject.CommonName
		out.DNSNames = append([]string(nil), c.DNSNames...)
		out.Issuer = c.Issuer.CommonName
		out.NotAfter = c.NotAfter
	}
	return out, nil
}
