package netstack

import (
	"encoding/binary"
	"fmt"
)

const (
	protoICMP = 1
	protoTCP  = 6
	protoUDP  = 17
)

type ipv4Packet struct {
	Src, Dst     [4]byte
	Proto        byte
	ID           uint16
	TTL          byte
	Payload      []byte
	HeaderLength int
}

func parseIPv4(raw []byte) (*ipv4Packet, error) {
	if len(raw) < 20 {
		return nil, fmt.Errorf("ipv4: truncated")
	}
	if raw[0]>>4 != 4 {
		return nil, fmt.Errorf("ipv4: version %d", raw[0]>>4)
	}
	ihl := int(raw[0]&0x0f) * 4
	if ihl < 20 || len(raw) < ihl {
		return nil, fmt.Errorf("ipv4: bad ihl")
	}
	total := int(binary.BigEndian.Uint16(raw[2:4]))
	if total < ihl || total > len(raw) {
		total = len(raw)
	}
	p := &ipv4Packet{
		Proto:        raw[9],
		ID:           binary.BigEndian.Uint16(raw[4:6]),
		TTL:          raw[8],
		Payload:      raw[ihl:total],
		HeaderLength: ihl,
	}
	copy(p.Src[:], raw[12:16])
	copy(p.Dst[:], raw[16:20])
	return p, nil
}

func encodeIPv4(src, dst [4]byte, proto byte, id uint16, payload []byte) []byte {
	ihl := 20
	total := ihl + len(payload)
	out := make([]byte, total)
	out[0] = 0x45
	binary.BigEndian.PutUint16(out[2:4], uint16(total))
	binary.BigEndian.PutUint16(out[4:6], id)
	out[8] = 64
	out[9] = proto
	copy(out[12:16], src[:])
	copy(out[16:20], dst[:])
	binary.BigEndian.PutUint16(out[10:12], checksum(out[:20]))
	copy(out[20:], payload)
	return out
}
