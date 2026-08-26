/**
 * VLESS wire-format — серверная сторона (Worker принимает подключение от
 * Go-ядра). Формат идентичен клиентской реализации в
 * `core/internal/adapters/transport/vlessproto/vless.go` — оба сверены с
 * исходниками xray-core независимо друг от друга (см.
 * docs/adr/0002-vless-reimplementation.md), см. комментарий там же про
 * причины переписывания вместо заимствования кода.
 *
 * Формат запроса (клиент → сервер):
 *   [1]  version = 0x00
 *   [16] UUID пользователя
 *   [1]  addons length = 0x00
 *   [1]  command = 0x01 (TCP) | 0x02 (UDP)
 *   [2]  port big-endian
 *   [1]  address type = 0x01 (IPv4) | 0x02 (domain) | 0x03 (IPv6)
 *   [N]  address
 *
 * Формат ответа (сервер → клиент):
 *   [1]  version
 *   [1]  addons length (здесь всегда 0x00)
 */

export const VLESS_VERSION = 0x00;

export const COMMAND_TCP = 0x01;
export const COMMAND_UDP = 0x02;

export const ADDR_TYPE_IPV4 = 0x01;
export const ADDR_TYPE_DOMAIN = 0x02;
export const ADDR_TYPE_IPV6 = 0x03;

export interface ParsedVlessRequest {
  userIdHex: string; // 32 hex-символа
  command: number;
  destHost: string;
  destPort: number;
  /** Смещение в исходном буфере сразу после заголовка — с него начинается payload. */
  headerLength: number;
}

export class VlessProtocolError extends Error {}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * parseRequestHeader разбирает заголовок VLESS-запроса из начала buf.
 * Бросает VlessProtocolError, если буфера недостаточно для полного
 * заголовка (вызывающая сторона должна докопить данные и повторить попытку
 * — типично для первого WS-фрейма, который может прийти частями).
 */
export function parseRequestHeader(buf: Uint8Array): ParsedVlessRequest {
  let offset = 0;

  const need = (n: number) => {
    if (buf.length < offset + n) {
      throw new VlessProtocolError(`incomplete header: need ${n} more bytes at offset ${offset}`);
    }
  };

  need(1);
  const version = buf[offset];
  offset += 1;
  if (version !== VLESS_VERSION) {
    throw new VlessProtocolError(`unsupported version ${version}`);
  }

  need(16);
  const userIdHex = bytesToHex(buf.subarray(offset, offset + 16));
  offset += 16;

  need(1);
  const addonsLen = buf[offset]!;
  offset += 1;
  need(addonsLen);
  offset += addonsLen; // addons в v1 не интерпретируются

  need(1);
  const command = buf[offset]!;
  offset += 1;
  if (command !== COMMAND_TCP && command !== COMMAND_UDP) {
    throw new VlessProtocolError(`unsupported command ${command}`);
  }

  need(2);
  const destPort = (buf[offset]! << 8) | buf[offset + 1]!;
  offset += 2;

  need(1);
  const addrType = buf[offset]!;
  offset += 1;

  let destHost: string;
  switch (addrType) {
    case ADDR_TYPE_IPV4: {
      need(4);
      destHost = Array.from(buf.subarray(offset, offset + 4)).join(".");
      offset += 4;
      break;
    }
    case ADDR_TYPE_DOMAIN: {
      need(1);
      const len = buf[offset]!;
      offset += 1;
      need(len);
      destHost = new TextDecoder().decode(buf.subarray(offset, offset + len));
      offset += len;
      break;
    }
    case ADDR_TYPE_IPV6: {
      need(16);
      const parts: string[] = [];
      for (let i = 0; i < 16; i += 2) {
        parts.push(((buf[offset + i]! << 8) | buf[offset + i + 1]!).toString(16));
      }
      destHost = parts.join(":");
      offset += 16;
      break;
    }
    default:
      throw new VlessProtocolError(`unsupported address type ${addrType}`);
  }

  return { userIdHex, command, destHost, destPort, headerLength: offset };
}

/** encodeResponseHeader — минимальный ответ сервера: версия + пустые addons. */
export function encodeResponseHeader(): Uint8Array {
  return new Uint8Array([VLESS_VERSION, 0x00]);
}
