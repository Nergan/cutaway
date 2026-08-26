import { describe, it, expect, vi, afterEach } from "vitest";
import { RestProxyUserRepository } from "../src/adapters/rest_proxy_user_repository.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("RestProxyUserRepository", () => {
  it("maps 404 to null on findClient", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(404, { detail: "not found" })),
    );
    const repo = new RestProxyUserRepository({ baseUrl: "https://origin.example", secret: "s" });
    expect(await repo.findClient("missing")).toBeNull();
  });

  it("maps a found client and sends the proxy secret", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        client_id: "dev-1",
        public_key_hex: "aa".repeat(32),
        vless_user_id_hex: "bb".repeat(16),
        is_banned: false,
        quota_limit_bytes: 10,
        bytes_used: 3,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const repo = new RestProxyUserRepository({ baseUrl: "https://origin.example/", secret: "sekrit" });
    const found = await repo.findClient("dev-1");
    expect(found?.clientId).toBe("dev-1");
    expect(found?.bytesUsed).toBe(3);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://origin.example/internal/v1/clients/find");
    expect((init.headers as Record<string, string>)["X-Another-Proxy-Secret"]).toBe("sekrit");
  });

  it("maps enrollment and consume", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { client_id: "dev-1", expires_at_unix_seconds: 1_700_000_000 }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const repo = new RestProxyUserRepository({ baseUrl: "https://origin.example", secret: "s" });
    const enrollment = await repo.findEnrollmentByTokenHash("deadbeef");
    expect(enrollment?.clientId).toBe("dev-1");
    await repo.consumeEnrollmentToken("deadbeef");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
