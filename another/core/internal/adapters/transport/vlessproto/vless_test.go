package vlessproto

import (
	"bufio"
	"bytes"
	"testing"
)

func TestEncodeRequestHeader_Domain(t *testing.T) {
	var buf bytes.Buffer
	userID := [16]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10}

	if err := EncodeRequestHeader(&buf, userID, CommandTCP, "example.com", 443); err != nil {
		t.Fatalf("EncodeRequestHeader: %v", err)
	}

	got := buf.Bytes()

	// [0] version
	if got[0] != Version {
		t.Errorf("version = %#x, want %#x", got[0], Version)
	}
	// [1:17] UUID
	if !bytes.Equal(got[1:17], userID[:]) {
		t.Errorf("UUID mismatch: got %x, want %x", got[1:17], userID)
	}
	// [17] addons length
	if got[17] != 0x00 {
		t.Errorf("addons length = %#x, want 0x00", got[17])
	}
	// [18] command
	if got[18] != CommandTCP {
		t.Errorf("command = %#x, want %#x", got[18], CommandTCP)
	}
	// [19:21] port big-endian 443 = 0x01BB
	if got[19] != 0x01 || got[20] != 0xBB {
		t.Errorf("port bytes = %#x %#x, want 0x01 0xBB", got[19], got[20])
	}
	// [21] address type = domain
	if got[21] != AddrTypeDomain {
		t.Errorf("addr type = %#x, want domain", got[21])
	}
	// [22] domain length
	if got[22] != byte(len("example.com")) {
		t.Errorf("domain length = %d, want %d", got[22], len("example.com"))
	}
	// [23:] domain bytes
	if string(got[23:23+len("example.com")]) != "example.com" {
		t.Errorf("domain = %q, want %q", got[23:], "example.com")
	}

	wantLen := 1 + 16 + 1 + 1 + 2 + 1 + 1 + len("example.com")
	if len(got) != wantLen {
		t.Errorf("total length = %d, want %d", len(got), wantLen)
	}
}

func TestEncodeRequestHeader_IPv4(t *testing.T) {
	var buf bytes.Buffer
	var userID [16]byte

	if err := EncodeRequestHeader(&buf, userID, CommandTCP, "1.2.3.4", 80); err != nil {
		t.Fatalf("EncodeRequestHeader: %v", err)
	}
	got := buf.Bytes()

	if got[21] != AddrTypeIPv4 {
		t.Errorf("addr type = %#x, want IPv4", got[21])
	}
	if !bytes.Equal(got[22:26], []byte{1, 2, 3, 4}) {
		t.Errorf("IPv4 bytes = %v, want [1 2 3 4]", got[22:26])
	}
	wantLen := 1 + 16 + 1 + 1 + 2 + 1 + 4
	if len(got) != wantLen {
		t.Errorf("total length = %d, want %d", len(got), wantLen)
	}
}

func TestDecodeResponseHeader_NoAddons(t *testing.T) {
	raw := []byte{Version, 0x00, 'h', 'e', 'l', 'l', 'o'} // version, addons_len=0, payload "hello"
	r := bufio.NewReader(bytes.NewReader(raw))

	if err := DecodeResponseHeader(r); err != nil {
		t.Fatalf("DecodeResponseHeader: %v", err)
	}

	rest := make([]byte, 5)
	if _, err := r.Read(rest); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if string(rest) != "hello" {
		t.Errorf("payload = %q, want %q", rest, "hello")
	}
}

func TestDecodeResponseHeader_WithAddons(t *testing.T) {
	raw := []byte{Version, 0x03, 0xAA, 0xBB, 0xCC, 'p', 'a', 'y', 'l', 'o', 'a', 'd'}
	r := bufio.NewReader(bytes.NewReader(raw))

	if err := DecodeResponseHeader(r); err != nil {
		t.Fatalf("DecodeResponseHeader: %v", err)
	}

	rest := make([]byte, 7)
	if _, err := r.Read(rest); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if string(rest) != "payload" {
		t.Errorf("payload = %q, want %q", rest, "payload")
	}
}

func TestDecodeResponseHeader_WrongVersion(t *testing.T) {
	raw := []byte{0x01, 0x00}
	r := bufio.NewReader(bytes.NewReader(raw))

	if err := DecodeResponseHeader(r); err != ErrUnsupportedVersion {
		t.Errorf("err = %v, want ErrUnsupportedVersion", err)
	}
}

func TestEncodeAddress_DomainTooLong(t *testing.T) {
	longHost := make([]byte, 256)
	for i := range longHost {
		longHost[i] = 'a'
	}
	var buf bytes.Buffer
	var userID [16]byte
	err := EncodeRequestHeader(&buf, userID, CommandTCP, string(longHost), 443)
	if err != ErrDomainTooLong {
		t.Errorf("err = %v, want ErrDomainTooLong", err)
	}
}

func TestDecodeRequestHeaderRoundTrip(t *testing.T) {
	var buf bytes.Buffer
	userID := [16]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10}
	if err := EncodeRequestHeader(&buf, userID, CommandTCP, "example.com", 443); err != nil {
		t.Fatal(err)
	}
	hdr, err := DecodeRequestHeader(bufio.NewReader(&buf))
	if err != nil {
		t.Fatal(err)
	}
	if hdr.DestHost != "example.com" || hdr.DestPort != 443 || hdr.Command != CommandTCP || hdr.UserID != userID {
		t.Fatalf("%+v", hdr)
	}
}
