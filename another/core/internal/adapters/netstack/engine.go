package netstack

import (
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"log/slog"
	"net/netip"
	"sync"
	"sync/atomic"
	"time"

	"github.com/another-vpn/another/core/internal/ports"
)

const (
	tcpFIN = 0x01
	tcpSYN = 0x02
	tcpRST = 0x04
	tcpPSH = 0x08
	tcpACK = 0x10
)

// Engine — userspace NAT: IP с TUN → TCP/UDP потоки через StreamDialer.
// Это не gVisor: только IPv4, TCP и UDP. DNS (udp/53) уходит в TCP:53
// через тот же dialer (Worker не умеет UDP).
type Engine struct {
	dev  ports.PacketDevice
	dial ports.StreamDialer
	log  *slog.Logger

	mu     sync.Mutex
	tcp    map[string]*tcpFlow
	udp    map[string]*udpFlow
	ipID   uint32
	closed atomic.Bool
	wg     sync.WaitGroup
	cancel context.CancelFunc
}

func NewEngine(dev ports.PacketDevice, dial ports.StreamDialer, log *slog.Logger) *Engine {
	if log == nil {
		log = slog.Default()
	}
	return &Engine{
		dev:  dev,
		dial: dial,
		log:  log,
		tcp:  make(map[string]*tcpFlow),
		udp:  make(map[string]*udpFlow),
	}
}

func (e *Engine) Run(ctx context.Context) error {
	ctx, e.cancel = context.WithCancel(ctx)
	buf := make([]byte, 2048)
	for {
		if e.closed.Load() {
			return nil
		}
		n, err := e.dev.ReadPacket(buf)
		if err != nil {
			if e.closed.Load() || ctx.Err() != nil {
				return nil
			}
			return err
		}
		pkt := append([]byte(nil), buf[:n]...)
		e.handlePacket(ctx, pkt)
	}
}

func (e *Engine) Close() error {
	e.closed.Store(true)
	if e.cancel != nil {
		e.cancel()
	}
	e.mu.Lock()
	for _, f := range e.tcp {
		f.close()
	}
	for _, f := range e.udp {
		f.close()
	}
	e.tcp = map[string]*tcpFlow{}
	e.udp = map[string]*udpFlow{}
	e.mu.Unlock()
	_ = e.dev.Close()
	e.wg.Wait()
	return nil
}

func (e *Engine) handlePacket(ctx context.Context, raw []byte) {
	ip, err := parseIPv4(raw)
	if err != nil {
		return
	}
	switch ip.Proto {
	case protoTCP:
		e.handleTCP(ctx, ip)
	case protoUDP:
		e.handleUDP(ctx, ip)
	default:
		// ICMP и прочее — дропаем; ping через VPN не обещаем в фазе 2.
	}
}

func flowKey(src, dst [4]byte, sport, dport uint16) string {
	return fmt.Sprintf("-%d-%d-%d", binary.BigEndian.Uint32(src[:]), sport, binary.BigEndian.Uint32(dst[:])) + fmt.Sprintf("-%d", dport)
}

func ipString(ip [4]byte) string {
	return netip.AddrFrom4(ip).String()
}

func (e *Engine) nextID() uint16 {
	return uint16(atomic.AddUint32(&e.ipID, 1))
}

func (e *Engine) writeIP(src, dst [4]byte, proto byte, payload []byte) {
	pkt := encodeIPv4(src, dst, proto, e.nextID(), payload)
	_ = e.dev.WritePacket(pkt)
}

type tcpHdr struct {
	SrcPort, DstPort uint16
	Seq, Ack         uint32
	DataOff          int
	Flags            byte
	Window           uint16
	Payload          []byte
}

func parseTCP(b []byte) (*tcpHdr, error) {
	if len(b) < 20 {
		return nil, io.ErrUnexpectedEOF
	}
	off := int(b[12]>>4) * 4
	if off < 20 || len(b) < off {
		return nil, io.ErrUnexpectedEOF
	}
	return &tcpHdr{
		SrcPort: binary.BigEndian.Uint16(b[0:2]),
		DstPort: binary.BigEndian.Uint16(b[2:4]),
		Seq:     binary.BigEndian.Uint32(b[4:8]),
		Ack:     binary.BigEndian.Uint32(b[8:12]),
		DataOff: off,
		Flags:   b[13],
		Window:  binary.BigEndian.Uint16(b[14:16]),
		Payload: b[off:],
	}, nil
}

func encodeTCP(srcPort, dstPort uint16, seq, ack uint32, flags byte, window uint16, src, dst [4]byte, payload []byte) []byte {
	hdr := make([]byte, 20+len(payload))
	binary.BigEndian.PutUint16(hdr[0:2], srcPort)
	binary.BigEndian.PutUint16(hdr[2:4], dstPort)
	binary.BigEndian.PutUint32(hdr[4:8], seq)
	binary.BigEndian.PutUint32(hdr[8:12], ack)
	hdr[12] = 5 << 4
	hdr[13] = flags
	binary.BigEndian.PutUint16(hdr[14:16], window)
	copy(hdr[20:], payload)
	binary.BigEndian.PutUint16(hdr[16:18], tcpUDPChecksum(src, dst, protoTCP, hdr))
	return hdr
}

type tcpFlow struct {
	e            *Engine
	src, dst     [4]byte
	sport, dport uint16
	recvNext     uint32
	sendNext     uint32
	remote       io.ReadWriteCloser
	mu           sync.Mutex
	closed       bool
}

func (f *tcpFlow) close() {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.closed {
		return
	}
	f.closed = true
	if f.remote != nil {
		_ = f.remote.Close()
	}
}

func (e *Engine) handleTCP(ctx context.Context, ip *ipv4Packet) {
	th, err := parseTCP(ip.Payload)
	if err != nil {
		return
	}
	key := flowKey(ip.Src, ip.Dst, th.SrcPort, th.DstPort)

	e.mu.Lock()
	flow := e.tcp[key]
	e.mu.Unlock()

	if th.Flags&tcpRST != 0 {
		if flow != nil {
			flow.close()
			e.mu.Lock()
			delete(e.tcp, key)
			e.mu.Unlock()
		}
		return
	}

	if flow == nil {
		if th.Flags&tcpSYN == 0 || th.Flags&tcpACK != 0 {
			return
		}
		flow = &tcpFlow{
			e:        e,
			src:      ip.Src,
			dst:      ip.Dst,
			sport:    th.SrcPort,
			dport:    th.DstPort,
			recvNext: th.Seq + 1,
			sendNext: uint32(time.Now().UnixNano()),
		}
		e.mu.Lock()
		e.tcp[key] = flow
		e.mu.Unlock()

		synack := encodeTCP(th.DstPort, th.SrcPort, flow.sendNext, flow.recvNext, tcpSYN|tcpACK, 65535, ip.Dst, ip.Src, nil)
		flow.sendNext++
		e.writeIP(ip.Dst, ip.Src, protoTCP, synack)

		e.wg.Add(1)
		go e.dialTCP(ctx, flow, key)
		return
	}

	if th.Flags&tcpFIN != 0 {
		flow.recvNext = th.Seq + 1
		ack := encodeTCP(flow.dport, flow.sport, flow.sendNext, flow.recvNext, tcpACK|tcpFIN, 65535, flow.dst, flow.src, nil)
		flow.sendNext++
		e.writeIP(flow.dst, flow.src, protoTCP, ack)
		flow.close()
		e.mu.Lock()
		delete(e.tcp, key)
		e.mu.Unlock()
		return
	}

	if len(th.Payload) == 0 {
		return
	}
	flow.recvNext = th.Seq + uint32(len(th.Payload))
	flow.mu.Lock()
	remote := flow.remote
	flow.mu.Unlock()
	if remote != nil {
		_, _ = remote.Write(th.Payload)
	}
	ack := encodeTCP(flow.dport, flow.sport, flow.sendNext, flow.recvNext, tcpACK, 65535, flow.dst, flow.src, nil)
	e.writeIP(flow.dst, flow.src, protoTCP, ack)
}

func (e *Engine) dialTCP(ctx context.Context, flow *tcpFlow, key string) {
	defer e.wg.Done()
	remote, err := e.dial(ctx, "tcp", ipString(flow.dst), flow.dport)
	if err != nil {
		e.log.Warn("tcp dial failed", "dst", ipString(flow.dst), "port", flow.dport, "error", err)
		rst := encodeTCP(flow.dport, flow.sport, flow.sendNext, flow.recvNext, tcpRST|tcpACK, 0, flow.dst, flow.src, nil)
		e.writeIP(flow.dst, flow.src, protoTCP, rst)
		flow.close()
		e.mu.Lock()
		delete(e.tcp, key)
		e.mu.Unlock()
		return
	}
	flow.mu.Lock()
	flow.remote = remote
	flow.mu.Unlock()

	buf := make([]byte, 16*1024)
	for {
		n, err := remote.Read(buf)
		if n > 0 {
			chunk := append([]byte(nil), buf[:n]...)
			seg := encodeTCP(flow.dport, flow.sport, flow.sendNext, flow.recvNext, tcpPSH|tcpACK, 65535, flow.dst, flow.src, chunk)
			flow.sendNext += uint32(n)
			e.writeIP(flow.dst, flow.src, protoTCP, seg)
		}
		if err != nil {
			fin := encodeTCP(flow.dport, flow.sport, flow.sendNext, flow.recvNext, tcpFIN|tcpACK, 65535, flow.dst, flow.src, nil)
			flow.sendNext++
			e.writeIP(flow.dst, flow.src, protoTCP, fin)
			flow.close()
			e.mu.Lock()
			delete(e.tcp, key)
			e.mu.Unlock()
			return
		}
	}
}

type udpFlow struct {
	remote       io.ReadWriteCloser
	src, dst     [4]byte
	sport, dport uint16
	e            *Engine
}

func (f *udpFlow) close() {
	if f.remote != nil {
		_ = f.remote.Close()
	}
}

func parseUDP(b []byte) (sport, dport uint16, payload []byte, err error) {
	if len(b) < 8 {
		return 0, 0, nil, io.ErrUnexpectedEOF
	}
	sport = binary.BigEndian.Uint16(b[0:2])
	dport = binary.BigEndian.Uint16(b[2:4])
	return sport, dport, b[8:], nil
}

func encodeUDP(srcPort, dstPort uint16, src, dst [4]byte, payload []byte) []byte {
	hdr := make([]byte, 8+len(payload))
	binary.BigEndian.PutUint16(hdr[0:2], srcPort)
	binary.BigEndian.PutUint16(hdr[2:4], dstPort)
	binary.BigEndian.PutUint16(hdr[4:6], uint16(8+len(payload)))
	copy(hdr[8:], payload)
	binary.BigEndian.PutUint16(hdr[6:8], tcpUDPChecksum(src, dst, protoUDP, hdr))
	return hdr
}

func (e *Engine) handleUDP(ctx context.Context, ip *ipv4Packet) {
	sport, dport, payload, err := parseUDP(ip.Payload)
	if err != nil {
		return
	}
	key := flowKey(ip.Src, ip.Dst, sport, dport)
	e.mu.Lock()
	flow := e.udp[key]
	e.mu.Unlock()
	if flow == nil {
		network := "udp"
		host := ipString(ip.Dst)
		port := dport
		if dport == 53 {
			// Worker — TCP-only. DNS через TCP:53, тот же dialer.
			network = "tcp"
		}
		remote, err := e.dial(ctx, network, host, port)
		if err != nil {
			e.log.Warn("udp dial failed", "dst", host, "port", port, "error", err)
			return
		}
		flow = &udpFlow{remote: remote, src: ip.Src, dst: ip.Dst, sport: sport, dport: dport, e: e}
		e.mu.Lock()
		e.udp[key] = flow
		e.mu.Unlock()
		e.wg.Add(1)
		go e.readUDP(flow, key, network)
	}
	if dport == 53 {
		var lenbuf [2]byte
		binary.BigEndian.PutUint16(lenbuf[:], uint16(len(payload)))
		_, _ = flow.remote.Write(lenbuf[:])
	}
	_, _ = flow.remote.Write(payload)
}

func (e *Engine) readUDP(flow *udpFlow, key, network string) {
	defer e.wg.Done()
	defer func() {
		flow.close()
		e.mu.Lock()
		delete(e.udp, key)
		e.mu.Unlock()
	}()
	buf := make([]byte, 64*1024)
	for {
		var payload []byte
		if network == "tcp" {
			var lenbuf [2]byte
			if _, err := io.ReadFull(flow.remote, lenbuf[:]); err != nil {
				return
			}
			n := int(binary.BigEndian.Uint16(lenbuf[:]))
			if n <= 0 || n > len(buf) {
				return
			}
			if _, err := io.ReadFull(flow.remote, buf[:n]); err != nil {
				return
			}
			payload = buf[:n]
		} else {
			n, err := flow.remote.Read(buf)
			if err != nil {
				return
			}
			payload = buf[:n]
		}
		seg := encodeUDP(flow.dport, flow.sport, flow.dst, flow.src, payload)
		e.writeIP(flow.dst, flow.src, protoUDP, seg)
	}
}
