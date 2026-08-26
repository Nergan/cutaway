package netstack

import (
	"context"
	"io"
	"testing"
	"time"

	"github.com/another-vpn/another/core/internal/ports"
)

func TestEngineUDPEcho(t *testing.T) {
	dev := NewMemoryDevice()
	dial := func(ctx context.Context, network, host string, port uint16) (ports.Tunnel, error) {
		r1, w1 := io.Pipe()
		return &pipeTunnel{r: r1, w: w1, echo: true}, nil
	}
	eng := NewEngine(dev, dial, nil)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _ = eng.Run(ctx) }()
	defer eng.Close()

	payload := []byte("hello-udp")
	pkt := ipv4UDPPacket([4]byte{10, 7, 0, 2}, [4]byte{1, 1, 1, 1}, 40000, 9, payload)
	dev.Inject(pkt)

	got, ok := dev.Receive(2 * time.Second)
	if !ok {
		t.Fatal("no reply packet")
	}
	ip, err := parseIPv4(got)
	if err != nil {
		t.Fatal(err)
	}
	_, _, body, err := parseUDP(ip.Payload)
	if err != nil {
		t.Fatal(err)
	}
	if string(body) != "hello-udp" {
		t.Fatalf("body = %q", body)
	}
}

func ipv4UDPPacket(src, dst [4]byte, sport, dport uint16, payload []byte) []byte {
	udp := encodeUDP(sport, dport, src, dst, payload)
	return encodeIPv4(src, dst, protoUDP, 1, udp)
}

type pipeTunnel struct {
	r    *io.PipeReader
	w    *io.PipeWriter
	echo bool
}

func (p *pipeTunnel) Read(b []byte) (int, error) { return p.r.Read(b) }
func (p *pipeTunnel) Write(b []byte) (int, error) {
	if p.echo {
		go func(data []byte) { _, _ = p.w.Write(data) }(append([]byte(nil), b...))
		return len(b), nil
	}
	return p.w.Write(b)
}
func (p *pipeTunnel) Close() error {
	_ = p.w.Close()
	return p.r.Close()
}

func TestChecksumIPv4Header(t *testing.T) {
	src := [4]byte{10, 0, 0, 1}
	dst := [4]byte{10, 0, 0, 2}
	pkt := encodeIPv4(src, dst, protoUDP, 7, []byte{1, 2, 3, 4})
	if checksum(pkt[:20]) != 0 {
		t.Fatal("ipv4 header checksum should verify to 0")
	}
}

func TestTCPParseRoundtripPorts(t *testing.T) {
	src := [4]byte{10, 7, 0, 2}
	dst := [4]byte{8, 8, 8, 8}
	seg := encodeTCP(1234, 443, 1, 2, tcpSYN, 65535, src, dst, nil)
	th, err := parseTCP(seg)
	if err != nil {
		t.Fatal(err)
	}
	if th.SrcPort != 1234 || th.DstPort != 443 || th.Flags&tcpSYN == 0 {
		t.Fatalf("%+v", th)
	}
}
