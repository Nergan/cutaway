// Package vlessproto — собственная реализация wire-format протокола VLESS
// (версия 0). Это НЕ заимствованный код: реализация написана с нуля на
// основе анализа формата байт в референсных проектах xray-core (MPL-2.0) и
// sing-box (GPL-3.0) — см. docs/adr/0002-vless-reimplementation.md. Опираться
// на анализ протокола можно и без переноса кода: сам by-byte формат
// сообщения — это факт совместимости протокола, а не объект авторского
// права; при этом мы сознательно не копируем ни одной строки их кода,
// поэтому лицензионные ограничения на этот пакет не переходят.
//
// Формат запроса (клиент → сервер), version 0, без XTLS flow (мы работаем
// поверх WebSocket, который уже туннелируется в TLS до CDN — доп. уровень
// XTLS Vision тут не нужен, это оптимизация для сырого TCP):
//
//	[1]  version                = 0x00
//	[16] UUID пользователя
//	[1]  addons length          = 0x00 (addons отсутствуют)
//	[1]  command                = 0x01 (TCP) | 0x02 (UDP)
//	[2]  port                   big-endian
//	[1]  address type           = 0x01 (IPv4) | 0x02 (domain) | 0x03 (IPv6)
//	[N]  address                domain: [1]len + bytes; IPv4: 4 bytes; IPv6: 16 bytes
//
// Формат ответа (сервер → клиент):
//
//	[1]  version                = 0x00 (должен совпадать с запросом)
//	[1]  addons length
//	[N]  addons (пропускаем, если length > 0 — в v1 не интерпретируем)
//
// После заголовка в обе стороны идёт сырой поток полезной нагрузки.
package vlessproto

import (
	"bufio"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
)

const (
	Version = byte(0x00)

	CommandTCP = byte(0x01)
	CommandUDP = byte(0x02)

	AddrTypeIPv4   = byte(0x01)
	AddrTypeDomain = byte(0x02)
	AddrTypeIPv6   = byte(0x03)
)

var (
	ErrUnsupportedVersion = errors.New("vlessproto: unsupported response version")
	ErrDomainTooLong      = errors.New("vlessproto: domain name longer than 255 bytes")
)

// EncodeRequestHeader кодирует заголовок VLESS-запроса в w. userID — 16 байт
// UUID пользователя (в нашей системе это UUID, привязанный к client_id на
// control-plane, не путать с Ed25519-идентичностью устройства — см. §11
// спецификации: Ed25519 используется для challenge-response аутентификации
// на control-plane, а VLESS UUID — это отдельный "билет" для data-plane,
// который control-plane выдаёт вместе с session_token).
func EncodeRequestHeader(w io.Writer, userID [16]byte, command byte, destHost string, destPort uint16) error {
	buf := make([]byte, 0, 64)
	buf = append(buf, Version)
	buf = append(buf, userID[:]...)
	buf = append(buf, 0x00) // addons length = 0 (без XTLS flow)
	buf = append(buf, command)

	portBytes := make([]byte, 2)
	binary.BigEndian.PutUint16(portBytes, destPort)
	buf = append(buf, portBytes...)

	addrBytes, err := encodeAddress(destHost)
	if err != nil {
		return err
	}
	buf = append(buf, addrBytes...)

	_, err = w.Write(buf)
	return err
}

// EncodeResponseHeader пишет ответ сервера (version + addons_len=0).
func EncodeResponseHeader(w io.Writer) error {
	_, err := w.Write([]byte{Version, 0x00})
	return err
}

func encodeAddress(host string) ([]byte, error) {
	if ip := net.ParseIP(host); ip != nil {
		if v4 := ip.To4(); v4 != nil {
			return append([]byte{AddrTypeIPv4}, v4...), nil
		}
		v6 := ip.To16()
		if v6 == nil {
			return nil, fmt.Errorf("vlessproto: invalid IP %q", host)
		}
		return append([]byte{AddrTypeIPv6}, v6...), nil
	}
	if len(host) > 255 {
		return nil, ErrDomainTooLong
	}
	out := make([]byte, 0, 2+len(host))
	out = append(out, AddrTypeDomain, byte(len(host)))
	out = append(out, host...)
	return out, nil
}

// DecodeResponseHeader читает и проверяет заголовок ответа сервера.
// Использует bufio.Reader, а не io.Reader напрямую, потому что вызывающая
// сторона (vless_ws.go) должна затем читать уже расшифрованную полезную
// нагрузку из того же потока без потери уже прочитанных, но не
// использованных байт.
func DecodeResponseHeader(r *bufio.Reader) error {
	version, err := r.ReadByte()
	if err != nil {
		return fmt.Errorf("vlessproto: read response version: %w", err)
	}
	if version != Version {
		return ErrUnsupportedVersion
	}
	addonsLen, err := r.ReadByte()
	if err != nil {
		return fmt.Errorf("vlessproto: read addons length: %w", err)
	}
	if addonsLen > 0 {
		if _, err := io.CopyN(io.Discard, r, int64(addonsLen)); err != nil {
			return fmt.Errorf("vlessproto: discard addons: %w", err)
		}
	}
	return nil
}

// RequestHeader — разобранный заголовок VLESS-запроса (после TLS/WS).
type RequestHeader struct {
	UserID   [16]byte
	Command  byte
	DestHost string
	DestPort uint16
}

// DecodeRequestHeader читает заголовок запроса. leftover полезной нагрузки
// остаётся в r.
func DecodeRequestHeader(r *bufio.Reader) (RequestHeader, error) {
	var out RequestHeader
	ver, err := r.ReadByte()
	if err != nil {
		return out, fmt.Errorf("vlessproto: read version: %w", err)
	}
	if ver != Version {
		return out, ErrUnsupportedVersion
	}
	if _, err := io.ReadFull(r, out.UserID[:]); err != nil {
		return out, fmt.Errorf("vlessproto: read uuid: %w", err)
	}
	addonLen, err := r.ReadByte()
	if err != nil {
		return out, fmt.Errorf("vlessproto: read addons length: %w", err)
	}
	if addonLen > 0 {
		if _, err := io.CopyN(io.Discard, r, int64(addonLen)); err != nil {
			return out, fmt.Errorf("vlessproto: discard addons: %w", err)
		}
	}
	out.Command, err = r.ReadByte()
	if err != nil {
		return out, fmt.Errorf("vlessproto: read command: %w", err)
	}
	var portBuf [2]byte
	if _, err := io.ReadFull(r, portBuf[:]); err != nil {
		return out, fmt.Errorf("vlessproto: read port: %w", err)
	}
	out.DestPort = binary.BigEndian.Uint16(portBuf[:])
	atyp, err := r.ReadByte()
	if err != nil {
		return out, fmt.Errorf("vlessproto: read atyp: %w", err)
	}
	switch atyp {
	case AddrTypeIPv4:
		var ip [4]byte
		if _, err := io.ReadFull(r, ip[:]); err != nil {
			return out, err
		}
		out.DestHost = net.IP(ip[:]).String()
	case AddrTypeIPv6:
		var ip [16]byte
		if _, err := io.ReadFull(r, ip[:]); err != nil {
			return out, err
		}
		out.DestHost = net.IP(ip[:]).String()
	case AddrTypeDomain:
		n, err := r.ReadByte()
		if err != nil {
			return out, err
		}
		b := make([]byte, n)
		if _, err := io.ReadFull(r, b); err != nil {
			return out, err
		}
		out.DestHost = string(b)
	default:
		return out, fmt.Errorf("vlessproto: bad atyp %#x", atyp)
	}
	return out, nil
}
