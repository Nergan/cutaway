import { describe, it, expect } from "vitest";
import { evaluateAccess } from "../src/domain/ban_policy.js";
import type { ClientRecord } from "../src/ports/user_repository_port.js";

function makeClient(overrides: Partial<ClientRecord> = {}): ClientRecord {
  return {
    clientId: "test-device",
    publicKeyHex: "aa".repeat(32),
    vlessUserIdHex: "bb".repeat(16),
    isBanned: false,
    quotaLimitBytes: 1000,
    bytesUsed: 0,
    ...overrides,
  };
}

describe("evaluateAccess", () => {
  it("allows a normal client under quota", () => {
    const result = evaluateAccess(makeClient());
    expect(result.allowed).toBe(true);
  });

  it("denies a banned client, even if under quota", () => {
    const result = evaluateAccess(makeClient({ isBanned: true }));
    expect(result.allowed).toBe(false);
    expect(result.reason).toBe("banned");
  });

  it("denies a client at or over quota", () => {
    const atLimit = evaluateAccess(makeClient({ bytesUsed: 1000, quotaLimitBytes: 1000 }));
    expect(atLimit.allowed).toBe(false);
    expect(atLimit.reason).toBe("quota_exceeded");

    const overLimit = evaluateAccess(makeClient({ bytesUsed: 1500, quotaLimitBytes: 1000 }));
    expect(overLimit.allowed).toBe(false);
    expect(overLimit.reason).toBe("quota_exceeded");
  });

  it("treats quotaLimitBytes = 0 as unlimited", () => {
    const result = evaluateAccess(makeClient({ quotaLimitBytes: 0, bytesUsed: 999_999 }));
    expect(result.allowed).toBe(true);
  });

  it("ban takes precedence over quota reason when both apply", () => {
    const result = evaluateAccess(makeClient({ isBanned: true, bytesUsed: 2000, quotaLimitBytes: 1000 }));
    expect(result.reason).toBe("banned");
  });
});
