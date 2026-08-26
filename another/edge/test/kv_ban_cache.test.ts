import { describe, it, expect, vi } from "vitest";
import { BAN_CACHE_TTL_SECONDS, KvBanCache } from "../src/adapters/kv_ban_cache.js";

function mockKv(overrides: Partial<KVNamespace> = {}): KVNamespace {
  return {
    get: vi.fn().mockResolvedValue(null),
    put: vi.fn().mockResolvedValue(undefined),
    delete: vi.fn().mockResolvedValue(undefined),
    list: vi.fn(),
    getWithMetadata: vi.fn(),
    ...overrides,
  } as unknown as KVNamespace;
}

describe("KvBanCache", () => {
  it("uses a KV TTL at or above the platform minimum of 60s", () => {
    expect(BAN_CACHE_TTL_SECONDS).toBeGreaterThanOrEqual(60);
  });

  it("writes the fallback decision with that TTL", async () => {
    const kv = mockKv();
    const cache = new KvBanCache(kv);
    await expect(cache.isBanned("dev-1", async () => false)).resolves.toBe(false);
    expect(kv.put).toHaveBeenCalledWith("ban:dev-1", "0", { expirationTtl: BAN_CACHE_TTL_SECONDS });
  });

  it("still returns the decision if KV put throws", async () => {
    const kv = mockKv({
      put: vi.fn().mockRejectedValue(new Error("TTL of 30 seconds is less than 60")),
    });
    const cache = new KvBanCache(kv);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      await expect(cache.isBanned("dev-1", async () => false)).resolves.toBe(false);
    } finally {
      errorSpy.mockRestore();
    }
  });
});
