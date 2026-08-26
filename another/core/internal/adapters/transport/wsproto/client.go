// Package wsproto — минимальный клиент WebSocket (RFC 6455), реализованный
// на чистом net/net.Conn/bufio/crypto без внешних зависимостей.
//
// Почему не gorilla/websocket: последняя версия тянет golang.org/x/net
// (нужен для необязательной SOCKS5-прокси поддержки), а домен golang.org не
// резолвится в нашем сетевом окружении сборки без доступа к
// proxy.golang.org — см. go.mod. Полноценный RFC 6455 клиент, ограниченный
// только тем, что реально нужно для транспорта VLESS (бинарные фреймы,
// без экстеншенов/компрессии), — это относительно небольшой и хорошо
// специфицированный протокол, который безопаснее держать под своим полным
// контролем, чем добавлять внешнюю зависимость ради одной функции.
//
// Ограничения v1 (осознанно не реализовано, т.к. не нужно для VLESS-WS):
//   - permessage-deflate и другие extensions
//   - text-фреймы (используются только binary)
//   - серверная сторона (нужен только клиент)
package wsproto

import (
	"bufio"
	"crypto/rand"
	"crypto/sha1"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net"
	"strings"
)

const wsGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

const (
	opContinuation = 0x0
	opText         = 0x1
	opBinary       = 0x2
	opClose        = 0x8
	opPing         = 0x9
	opPong         = 0xA
)

var (
	ErrHandshakeFailed  = errors.New("wsproto: handshake failed")
	ErrConnectionClosed = errors.New("wsproto: connection closed by peer")
)

// Handshake выполняет клиентское HTTP-рукопожатие апгрейда до WebSocket поверх
// уже установленного conn (который может быть как обычным net.Conn, так и
// *tls.Conn — вызывающая сторона отвечает за TLS). extraHeaders позволяет
// передать Host/произвольные заголовки (напр. маскировку под браузер).
func Handshake(conn net.Conn, path, host string, extraHeaders map[string]string) (*Conn, error) {
	keyBytes := make([]byte, 16)
	if _, err := rand.Read(keyBytes); err != nil {
		return nil, fmt.Errorf("wsproto: generate key: %w", err)
	}
	key := base64.StdEncoding.EncodeToString(keyBytes)

	var req strings.Builder
	fmt.Fprintf(&req, "GET %s HTTP/1.1\r\n", path)
	fmt.Fprintf(&req, "Host: %s\r\n", host)
	req.WriteString("Upgrade: websocket\r\n")
	req.WriteString("Connection: Upgrade\r\n")
	fmt.Fprintf(&req, "Sec-WebSocket-Key: %s\r\n", key)
	req.WriteString("Sec-WebSocket-Version: 13\r\n")
	for k, v := range extraHeaders {
		fmt.Fprintf(&req, "%s: %s\r\n", k, v)
	}
	req.WriteString("\r\n")

	if _, err := conn.Write([]byte(req.String())); err != nil {
		return nil, fmt.Errorf("wsproto: write handshake request: %w", err)
	}

	br := bufio.NewReader(conn)
	statusLine, err := br.ReadString('\n')
	if err != nil {
		return nil, fmt.Errorf("wsproto: read status line: %w", err)
	}
	if !strings.Contains(statusLine, "101") {
		return nil, fmt.Errorf("%w: unexpected status line %q", ErrHandshakeFailed, strings.TrimSpace(statusLine))
	}

	var acceptGot string
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			return nil, fmt.Errorf("wsproto: read headers: %w", err)
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			break // конец заголовков
		}
		if idx := strings.IndexByte(line, ':'); idx > 0 {
			name := strings.TrimSpace(line[:idx])
			value := strings.TrimSpace(line[idx+1:])
			if strings.EqualFold(name, "Sec-WebSocket-Accept") {
				acceptGot = value
			}
		}
	}

	sum := sha1.Sum([]byte(key + wsGUID))
	acceptWant := base64.StdEncoding.EncodeToString(sum[:])
	if acceptGot != acceptWant {
		return nil, fmt.Errorf("%w: Sec-WebSocket-Accept mismatch", ErrHandshakeFailed)
	}

	return &Conn{conn: conn, br: br}, nil
}

// Conn — установленное WebSocket-соединение, реализует io.ReadWriteCloser
// поверх бинарных фреймов. Write отправляет один замаскированный (клиент
// обязан маскировать по RFC 6455 §5.1) binary-фрейм на каждый вызов.
// Read отдаёт данные из текущего входящего сообщения, при необходимости
// читая и склеивая continuation-фреймы; ping отвечает pong прозрачно.
type Conn struct {
	conn net.Conn
	br   *bufio.Reader

	pending []byte // остаток недочитанного сообщения между вызовами Read
}

func (c *Conn) Write(p []byte) (int, error) {
	if err := c.writeFrame(opBinary, p); err != nil {
		return 0, err
	}
	return len(p), nil
}

func (c *Conn) writeFrame(opcode byte, payload []byte) error {
	var header []byte
	finOp := byte(0x80) | opcode // FIN=1

	length := len(payload)
	switch {
	case length <= 125:
		header = []byte{finOp, 0x80 | byte(length)}
	case length <= 65535:
		header = []byte{finOp, 0x80 | 126, byte(length >> 8), byte(length)}
	default:
		header = make([]byte, 10)
		header[0] = finOp
		header[1] = 0x80 | 127
		for i := 0; i < 8; i++ {
			header[9-i] = byte(length >> (8 * i))
		}
	}

	maskKey := make([]byte, 4)
	if _, err := rand.Read(maskKey); err != nil {
		return fmt.Errorf("wsproto: generate mask key: %w", err)
	}
	header = append(header, maskKey...)

	masked := make([]byte, length)
	for i := 0; i < length; i++ {
		masked[i] = payload[i] ^ maskKey[i%4]
	}

	if _, err := c.conn.Write(header); err != nil {
		return fmt.Errorf("wsproto: write frame header: %w", err)
	}
	if length > 0 {
		if _, err := c.conn.Write(masked); err != nil {
			return fmt.Errorf("wsproto: write frame payload: %w", err)
		}
	}
	return nil
}

func (c *Conn) Read(p []byte) (int, error) {
	for len(c.pending) == 0 {
		if err := c.readMessage(); err != nil {
			return 0, err
		}
	}
	n := copy(p, c.pending)
	c.pending = c.pending[n:]
	return n, nil
}

// readMessage читает одно логическое сообщение (один или несколько
// continuation-фреймов) в c.pending; служебные фреймы (ping/pong/close)
// обрабатывает прозрачно и не возвращает вызывающей стороне.
func (c *Conn) readMessage() error {
	var message []byte
	first := true
	var messageOpcode byte

	for {
		fin, opcode, payload, err := c.readFrame()
		if err != nil {
			return err
		}

		switch opcode {
		case opPing:
			if err := c.writeFrame(opPong, payload); err != nil {
				return err
			}
			continue
		case opPong:
			continue
		case opClose:
			_ = c.writeFrame(opClose, nil)
			return ErrConnectionClosed
		}

		if first {
			messageOpcode = opcode
			first = false
		} else if opcode != opContinuation {
			return fmt.Errorf("wsproto: unexpected opcode %#x mid-message", opcode)
		}

		message = append(message, payload...)
		if fin {
			break
		}
	}

	if messageOpcode != opBinary && messageOpcode != opText {
		// Не бинарное и не текстовое сообщение верхнего уровня — пропускаем
		// (в VLESS-WS не ожидается ничего кроме binary, но не считаем это
		// фатальной ошибкой).
		return c.readMessage()
	}

	c.pending = message
	return nil
}

func (c *Conn) readFrame() (fin bool, opcode byte, payload []byte, err error) {
	head := make([]byte, 2)
	if _, err = io.ReadFull(c.br, head); err != nil {
		return false, 0, nil, fmt.Errorf("wsproto: read frame header: %w", err)
	}

	fin = head[0]&0x80 != 0
	opcode = head[0] & 0x0F
	masked := head[1]&0x80 != 0
	length := uint64(head[1] & 0x7F)

	switch length {
	case 126:
		ext := make([]byte, 2)
		if _, err = io.ReadFull(c.br, ext); err != nil {
			return false, 0, nil, fmt.Errorf("wsproto: read extended length: %w", err)
		}
		length = uint64(ext[0])<<8 | uint64(ext[1])
	case 127:
		ext := make([]byte, 8)
		if _, err = io.ReadFull(c.br, ext); err != nil {
			return false, 0, nil, fmt.Errorf("wsproto: read extended length: %w", err)
		}
		length = 0
		for i := 0; i < 8; i++ {
			length = length<<8 | uint64(ext[i])
		}
	}

	var maskKey []byte
	if masked {
		maskKey = make([]byte, 4)
		if _, err = io.ReadFull(c.br, maskKey); err != nil {
			return false, 0, nil, fmt.Errorf("wsproto: read mask key: %w", err)
		}
	}

	payload = make([]byte, length)
	if length > 0 {
		if _, err = io.ReadFull(c.br, payload); err != nil {
			return false, 0, nil, fmt.Errorf("wsproto: read frame payload: %w", err)
		}
	}
	if masked {
		for i := range payload {
			payload[i] ^= maskKey[i%4]
		}
	}

	return fin, opcode, payload, nil
}

func (c *Conn) Close() error {
	_ = c.writeFrame(opClose, nil)
	return c.conn.Close()
}
