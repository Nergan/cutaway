package wsproto

import (
	"bufio"
	"bytes"
	"crypto/sha1"
	"encoding/base64"
	"fmt"
	"io"
	"net"
	"strings"
	"testing"
	"time"
)

// fakeServerHandshake читает HTTP-запрос апгрейда из conn и отвечает валидным
// 101 Switching Protocols — минимальная серверная сторона, нужна только для
// тестов клиента выше в этом же пакете.
func fakeServerHandshake(t *testing.T, conn net.Conn) {
	t.Helper()
	br := bufio.NewReader(conn)
	var key string
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			t.Fatalf("server: read request: %v", err)
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			break
		}
		if idx := strings.IndexByte(line, ':'); idx > 0 {
			name := strings.TrimSpace(line[:idx])
			if strings.EqualFold(name, "Sec-WebSocket-Key") {
				key = strings.TrimSpace(line[idx+1:])
			}
		}
	}
	sum := sha1.Sum([]byte(key + wsGUID))
	accept := base64.StdEncoding.EncodeToString(sum[:])

	resp := "HTTP/1.1 101 Switching Protocols\r\n" +
		"Upgrade: websocket\r\n" +
		"Connection: Upgrade\r\n" +
		"Sec-WebSocket-Accept: " + accept + "\r\n\r\n"
	if _, err := conn.Write([]byte(resp)); err != nil {
		t.Fatalf("server: write response: %v", err)
	}
}

// serverWriteFrame пишет НЕзамаскированный фрейм (сервер по RFC 6455 не
// обязан маскировать исходящие фреймы).
func serverWriteFrame(conn net.Conn, opcode byte, fin bool, payload []byte) error {
	finBit := byte(0)
	if fin {
		finBit = 0x80
	}
	var out []byte
	length := len(payload)
	switch {
	case length <= 125:
		out = []byte{finBit | opcode, byte(length)}
	case length <= 65535:
		out = []byte{finBit | opcode, 126, byte(length >> 8), byte(length)}
	default:
		panic("serverWriteFrame: payload too large for this test helper")
	}
	out = append(out, payload...)
	_, err := conn.Write(out)
	return err
}

// serverReadFrame читает один (замаскированный, т.к. пришёл от клиента) фрейм.
func serverReadFrame(br *bufio.Reader) (opcode byte, payload []byte, err error) {
	head := make([]byte, 2)
	if _, err = io.ReadFull(br, head); err != nil {
		return 0, nil, err
	}
	opcode = head[0] & 0x0F
	masked := head[1]&0x80 != 0
	length := int(head[1] & 0x7F)
	if length == 126 {
		ext := make([]byte, 2)
		if _, err = io.ReadFull(br, ext); err != nil {
			return 0, nil, err
		}
		length = int(ext[0])<<8 | int(ext[1])
	}
	var maskKey []byte
	if masked {
		maskKey = make([]byte, 4)
		if _, err = io.ReadFull(br, maskKey); err != nil {
			return 0, nil, err
		}
	}
	payload = make([]byte, length)
	if _, err = io.ReadFull(br, payload); err != nil {
		return 0, nil, err
	}
	if masked {
		for i := range payload {
			payload[i] ^= maskKey[i%4]
		}
	}
	return opcode, payload, nil
}

func TestHandshakeAndEcho(t *testing.T) {
	clientConn, serverConn := net.Pipe()
	defer clientConn.Close()
	defer serverConn.Close()

	serverDone := make(chan error, 1)
	go func() {
		fakeServerHandshake(t, serverConn)
		br := bufio.NewReader(serverConn)
		opcode, payload, err := serverReadFrame(br)
		if err != nil {
			serverDone <- fmt.Errorf("server read: %w", err)
			return
		}
		if opcode != opBinary {
			serverDone <- fmt.Errorf("server: opcode = %#x, want binary", opcode)
			return
		}
		// эхо обратно, немаскированным фреймом
		if err := serverWriteFrame(serverConn, opBinary, true, payload); err != nil {
			serverDone <- fmt.Errorf("server write: %w", err)
			return
		}
		serverDone <- nil
	}()

	wsConn, err := Handshake(clientConn, "/vless", "example.com", nil)
	if err != nil {
		t.Fatalf("Handshake: %v", err)
	}

	sent := []byte("hello vless over websocket")
	if _, err := wsConn.Write(sent); err != nil {
		t.Fatalf("Write: %v", err)
	}

	got := make([]byte, len(sent))
	if _, err := io.ReadFull(wsConn, got); err != nil {
		t.Fatalf("Read: %v", err)
	}
	if !bytes.Equal(got, sent) {
		t.Errorf("echo mismatch: got %q, want %q", got, sent)
	}

	select {
	case err := <-serverDone:
		if err != nil {
			t.Fatalf("server goroutine: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for server goroutine")
	}
}

func TestHandshake_RejectsBadStatus(t *testing.T) {
	clientConn, serverConn := net.Pipe()
	defer clientConn.Close()

	go func() {
		br := bufio.NewReader(serverConn)
		for {
			line, err := br.ReadString('\n')
			if err != nil || strings.TrimSpace(line) == "" {
				break
			}
		}
		serverConn.Write([]byte("HTTP/1.1 404 Not Found\r\n\r\n"))
		serverConn.Close()
	}()

	_, err := Handshake(clientConn, "/vless", "example.com", nil)
	if err == nil {
		t.Fatal("expected error for non-101 response, got nil")
	}
}

func TestReadHandlesFragmentedMessage(t *testing.T) {
	clientConn, serverConn := net.Pipe()
	defer clientConn.Close()
	defer serverConn.Close()

	go func() {
		fakeServerHandshake(t, serverConn)
		// два continuation-фрейма, составляющие одно сообщение
		serverWriteFrame(serverConn, opBinary, false, []byte("part1-"))
		serverWriteFrame(serverConn, opContinuation, true, []byte("part2"))
	}()

	wsConn, err := Handshake(clientConn, "/vless", "example.com", nil)
	if err != nil {
		t.Fatalf("Handshake: %v", err)
	}

	got := make([]byte, len("part1-part2"))
	if _, err := io.ReadFull(wsConn, got); err != nil {
		t.Fatalf("Read: %v", err)
	}
	if string(got) != "part1-part2" {
		t.Errorf("got %q, want %q", got, "part1-part2")
	}
}
