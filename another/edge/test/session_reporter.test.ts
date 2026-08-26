import { describe, it, expect, vi, afterEach } from "vitest";
import { clientIp, hashIp, reportAuthOutcome } from "../src/adapters/session_reporter.js";
import type { Env } from "../src/env.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakeEnv(overrides: Partial<Env> = {}): Env {
  return {
    NONCE_LEDGER: {} as Env["NONCE_LEDGER"],
    BAN_CACHE: {} as Env["BAN_CACHE"],
    MONGO_REST_PROXY_URL: "https://origin.example",
    ANOTHER_SERVICE_SECRET: "sekrit",
    NODES_JSON: "[]",
    ...overrides,
  };
}

describe("session_reporter", () => {
  it("hashes IP with secret (not raw IP)", async () => {
    const a = await hashIp("1.2.3.4", "sekrit");
    const b = await hashIp("1.2.3.4", "other");
    const c = await hashIp("5.6.7.8", "sekrit");
    expect(a).toHaveLength(16);
    expect(a).not.toBe(b);
    expect(a).not.toBe(c);
    expect(a).not.toContain("1.2.3.4");
  });

  it("prefers CF-Connecting-IP", () => {
    const req = new Request("https://edge.example/auth", {
      headers: {
        "CF-Connecting-IP": "203.0.113.9",
        "X-Forwarded-For": "10.0.0.1",
      },
    });
    expect(clientIp(req)).toBe("203.0.113.9");
  });

  it("posts auth_fail on 4xx and upserts session on 200", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const peek = new Request("https://edge.example/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json", "CF-Connecting-IP": "203.0.113.9" },
      body: JSON.stringify({ client_id: "dev-1", signature: "aa", timestamp: 1, nonce: "n" }),
    });
    const original = peek.clone();

    await reportAuthOutcome(fakeEnv(), peek.clone(), new Response("no", { status: 403 }), original);
    const failCall = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/internal/v1/events"));
    expect(failCall).toBeTruthy();
    expect(JSON.parse(String((failCall![1] as RequestInit).body))).toMatchObject({
      category: "auth_fail",
      client_id: "dev-1",
    });

    fetchMock.mockClear();
    const peekOk = new Request("https://edge.example/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json", "CF-Connecting-IP": "203.0.113.9" },
      body: JSON.stringify({ client_id: "dev-1", signature: "aa", timestamp: 1, nonce: "n" }),
    });
    await reportAuthOutcome(fakeEnv(), peekOk.clone(), new Response("{}", { status: 200 }), peekOk);
    const upsert = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/internal/v1/sessions/upsert"));
    expect(upsert).toBeTruthy();
    const body = JSON.parse(String((upsert![1] as RequestInit).body));
    expect(body.client_id).toBe("dev-1");
    expect(body.ip_hash).toHaveLength(16);
    expect(body.ip).toBeNull();
  });
});
