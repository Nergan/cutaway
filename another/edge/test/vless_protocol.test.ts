import { describe, it, expect } from "vitest";
import {
  parseRequestHeader,
  encodeResponseHeader,
  VlessProtocolError,
  VLESS_VERSION,
  COMMAND_TCP,
  ADDR_TYPE_DOMAIN,
  ADDR_TYPE_IPV4,
} from "../src/domain/vless_protocol.js";

/** Собирает валидный запрос вручную — независимо от Go-реализации, чтобы
 * тест реально проверял совместимость форматов, а не сам себя. */
function buildRequest(opts: { userId?: number[]; command?: number; port?: number; addrType?: number; addr?: number[] }): Uint8Array {
  const userId = opts.userId ?? Array.from({ length: 16 }, (_, i) => i + 1);
  const command = opts.command ?? COMMAND_TCP;
  const port = opts.port ?? 443;
  const addrType = opts.addrType ?? ADDR_TYPE_DOMAIN;
  const addr = opts.addr ?? [11, ...Array.from("example.com").map((c) => c.charCodeAt(0))];

  return new Uint8Array([VLESS_VERSION, ...userId, 0x00, command, (port >> 8) & 0xff, port & 0xff, addrType, ...addr]);
}

describe("parseRequestHeader", () => {
  it("parses a domain-based request matching the Go client's wire format", () => {
    const buf = buildRequest({});
    const parsed = parseRequestHeader(buf);

    expect(parsed.userIdHex).toBe("0102030405060708090a0b0c0d0e0f10");
    expect(parsed.command).toBe(COMMAND_TCP);
    expect(parsed.destHost).toBe("example.com");
    expect(parsed.destPort).toBe(443);
    expect(parsed.headerLength).toBe(buf.length);
  });

  it("parses an IPv4-based request", () => {
    const buf = buildRequest({ addrType: ADDR_TYPE_IPV4, addr: [1, 2, 3, 4], port: 80 });
    const parsed = parseRequestHeader(buf);

    expect(parsed.destHost).toBe("1.2.3.4");
    expect(parsed.destPort).toBe(80);
  });

  it("throws VlessProtocolError with 'incomplete header' when buffer is truncated", () => {
    const full = buildRequest({});
    const truncated = full.subarray(0, 10);

    expect(() => parseRequestHeader(truncated)).toThrow(VlessProtocolError);
    try {
      parseRequestHeader(truncated);
    } catch (err) {
      expect((err as Error).message).toMatch(/^incomplete header/);
    }
  });

  it("rejects unsupported version", () => {
    const buf = buildRequest({});
    buf[0] = 0x01;
    expect(() => parseRequestHeader(buf)).toThrow(/unsupported version/);
  });

  it("computes headerLength correctly when payload follows the header", () => {
    const header = buildRequest({});
    const payload = new TextEncoder().encode("payload-bytes");
    const combined = new Uint8Array(header.length + payload.length);
    combined.set(header, 0);
    combined.set(payload, header.length);

    const parsed = parseRequestHeader(combined);
    expect(parsed.headerLength).toBe(header.length);

    const remainder = combined.subarray(parsed.headerLength);
    expect(new TextDecoder().decode(remainder)).toBe("payload-bytes");
  });
});

describe("encodeResponseHeader", () => {
  it("encodes version + zero-length addons", () => {
    const resp = encodeResponseHeader();
    expect(Array.from(resp)).toEqual([VLESS_VERSION, 0x00]);
  });
});

describe("interop with core/internal/adapters/transport/vlessproto (Go)", () => {
  it("decodes a golden byte vector produced by the actual Go encoder", () => {
    // Сгенерировано командой `go run` поверх той же логики, что в
    // core/internal/adapters/transport/vlessproto/vless.go — байт-в-байт,
    // а не переписано вручную здесь, чтобы тест реально ловил расхождение
    // форматов между Go- и TS-стороной, а не сравнивал TS сам с собой.
    const goldenHex =
      "000102030405060708090a0b0c0d0e0f10000101bb020b6578616d706c652e636f6d7061796c6f61642d61667465722d686561646572";
    const buf = new Uint8Array(goldenHex.match(/.{1,2}/g)!.map((b) => parseInt(b, 16)));

    const parsed = parseRequestHeader(buf);

    expect(parsed.userIdHex).toBe("0102030405060708090a0b0c0d0e0f10");
    expect(parsed.command).toBe(COMMAND_TCP);
    expect(parsed.destHost).toBe("example.com");
    expect(parsed.destPort).toBe(443);

    const remainder = buf.subarray(parsed.headerLength);
    expect(new TextDecoder().decode(remainder)).toBe("payload-after-header");
  });
});
