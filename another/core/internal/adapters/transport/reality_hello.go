package transport

import (
	"encoding/binary"
	"fmt"
	"io"
)

const (
	extServerName = 0x0000
	extKeyShare   = 0x0033
	groupX25519   = 0x001d
)

type parsedClientHello struct {
	Record    []byte
	Handshake []byte
	Random    [32]byte
	SessionID []byte
	Suites    []uint16
	SNI       string
	X25519Pub []byte
}

func readTLSRecord(r io.Reader) ([]byte, []byte, error) {
	hdr := make([]byte, 5)
	if _, err := io.ReadFull(r, hdr); err != nil {
		return nil, nil, err
	}
	if hdr[0] != 0x16 {
		return nil, nil, fmt.Errorf("reality: not a handshake record (type=%d)", hdr[0])
	}
	n := int(binary.BigEndian.Uint16(hdr[3:5]))
	if n < 4 || n > 16*1024 {
		return nil, nil, fmt.Errorf("reality: bad record length %d", n)
	}
	body := make([]byte, n)
	if _, err := io.ReadFull(r, body); err != nil {
		return nil, nil, err
	}
	record := append(hdr, body...)
	return record, body, nil
}

func parseClientHello(handshake []byte) (parsedClientHello, error) {
	var out parsedClientHello
	out.Handshake = handshake
	if len(handshake) < 40 || handshake[0] != 0x01 {
		return out, fmt.Errorf("reality: not ClientHello")
	}
	hsLen := int(handshake[1])<<16 | int(handshake[2])<<8 | int(handshake[3])
	if 4+hsLen > len(handshake) {
		return out, fmt.Errorf("reality: truncated ClientHello")
	}
	p := handshake[4 : 4+hsLen]
	if len(p) < 34 {
		return out, fmt.Errorf("reality: ClientHello too short")
	}
	copy(out.Random[:], p[2:34])
	sidLen := int(p[34])
	if 35+sidLen > len(p) {
		return out, fmt.Errorf("reality: bad session id")
	}
	out.SessionID = append([]byte(nil), p[35:35+sidLen]...)
	off := 35 + sidLen
	if off+2 > len(p) {
		return out, fmt.Errorf("reality: no cipher suites")
	}
	csLen := int(binary.BigEndian.Uint16(p[off : off+2]))
	off += 2
	if off+csLen+1 > len(p) || csLen%2 != 0 {
		return out, fmt.Errorf("reality: bad cipher suites")
	}
	for i := 0; i < csLen; i += 2 {
		out.Suites = append(out.Suites, binary.BigEndian.Uint16(p[off+i:off+i+2]))
	}
	off += csLen
	compLen := int(p[off])
	off++
	if off+compLen+2 > len(p) {
		return out, fmt.Errorf("reality: bad compression")
	}
	off += compLen
	extLen := int(binary.BigEndian.Uint16(p[off : off+2]))
	off += 2
	end := off + extLen
	if end > len(p) {
		return out, fmt.Errorf("reality: truncated extensions")
	}
	for off+4 <= end {
		typ := binary.BigEndian.Uint16(p[off : off+2])
		n := int(binary.BigEndian.Uint16(p[off+2 : off+4]))
		off += 4
		if off+n > end {
			return out, fmt.Errorf("reality: bad extension")
		}
		data := p[off : off+n]
		off += n
		switch typ {
		case extServerName:
			out.SNI = parseSNI(data)
		case extKeyShare:
			out.X25519Pub = parseX25519Share(data)
		}
	}
	return out, nil
}

func parseSNI(data []byte) string {
	if len(data) < 5 {
		return ""
	}
	listLen := int(binary.BigEndian.Uint16(data[0:2]))
	if 2+listLen > len(data) {
		return ""
	}
	p := data[2 : 2+listLen]
	if len(p) < 3 || p[0] != 0 {
		return ""
	}
	n := int(binary.BigEndian.Uint16(p[1:3]))
	if 3+n > len(p) {
		return ""
	}
	return string(p[3 : 3+n])
}

func parseX25519Share(data []byte) []byte {
	if len(data) < 2 {
		return nil
	}
	listLen := int(binary.BigEndian.Uint16(data[0:2]))
	p := data[2:]
	if listLen > len(p) {
		p = data[2:]
	} else {
		p = data[2 : 2+listLen]
	}
	const groupX25519MLKEM = 0x11ec
	var classic, hybrid []byte
	for len(p) >= 4 {
		group := binary.BigEndian.Uint16(p[0:2])
		n := int(binary.BigEndian.Uint16(p[2:4]))
		p = p[4:]
		if n > len(p) {
			return nil
		}
		if group == groupX25519 && n == 32 && classic == nil {
			classic = append([]byte(nil), p[:n]...)
		}
		if (group == groupX25519MLKEM || group == 0x6399) && n >= 32 && hybrid == nil {
			hybrid = append([]byte(nil), p[n-32:n]...)
		}
		p = p[n:]
	}
	if classic != nil {
		return classic
	}
	return hybrid
}

func aadWithZeroSessionID(handshake []byte) []byte {
	aad := append([]byte(nil), handshake...)
	if len(aad) < 71 {
		return aad
	}
	// handshake[38] is session_id_len (after 4-byte hs header + 2 ver + 32 random).
	if aad[38] == 32 {
		for i := 39; i < 71; i++ {
			aad[i] = 0
		}
	}
	return aad
}
