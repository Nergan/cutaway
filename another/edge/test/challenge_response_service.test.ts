import { describe, it, expect, vi } from "vitest";
import { AuthError, handleChallengeResponse, type ChallengeResponseDeps } from "../src/domain/challenge_response_service.js";
import type { ClientRecord } from "../src/ports/user_repository_port.js";
import type { SessionInfo } from "../src/ports/session_store_port.js";

function makeClient(overrides: Partial<ClientRecord> = {}): ClientRecord {
  return {
    clientId: "test-device",
    publicKeyHex: "aa".repeat(32),
    vlessUserIdHex: "bb".repeat(16),
    isBanned: false,
    quotaLimitBytes: 0,
    bytesUsed: 0,
    ...overrides,
  };
}

/** Собирает ChallengeResponseDeps с моками портов; каждый мок можно
 * переопределить в конкретном тесте. */
function makeDeps(overrides: Partial<ChallengeResponseDeps> = {}, client: ClientRecord | null = makeClient()): ChallengeResponseDeps {
  const savedSessions = new Map<string, SessionInfo>();

  return {
    nonceStore: {
      issueNonce: vi.fn().mockResolvedValue("test-nonce"),
      consumeNonce: vi.fn().mockResolvedValue(true),
    },
    userRepo: {
      findClient: vi.fn().mockResolvedValue(client),
      findEnrollmentByTokenHash: vi.fn(),
      bindDeviceIdentity: vi.fn(),
      consumeEnrollmentToken: vi.fn(),
      incrementUsage: vi.fn(),
    },
    verifier: {
      verify: vi.fn().mockResolvedValue(true),
    },
    clock: {
      nowUnixSeconds: () => 1_000_000,
    },
    banCache: {
      isBanned: vi.fn().mockImplementation((_id, fallback) => fallback()),
      invalidate: vi.fn(),
    },
    sessionStore: {
      save: vi.fn().mockImplementation(async (token, info) => {
        savedSessions.set(token, info);
      }),
      validate: vi.fn().mockImplementation(async (token) => savedSessions.get(token) ?? null),
    },
    generateSessionToken: () => "generated-session-token",
    ...overrides,
  };
}

const validRequest = {
  clientId: "test-device",
  signatureHex: "cc".repeat(64),
  timestampUnixSeconds: 1_000_000,
  nonce: "test-nonce",
};

describe("handleChallengeResponse", () => {
  it("succeeds for a valid request and persists the session", async () => {
    const deps = makeDeps();
    const result = await handleChallengeResponse(deps, validRequest);

    expect(result.sessionToken).toBe("generated-session-token");
    expect(result.vlessUserIdHex).toBe("bb".repeat(16));
    expect(deps.sessionStore.save).toHaveBeenCalledWith(
      "generated-session-token",
      { clientId: "test-device", vlessUserIdHex: "bb".repeat(16) },
      expect.any(Number),
    );
  });

  it("rejects requests outside the sliding time window", async () => {
    const deps = makeDeps();
    await expect(
      handleChallengeResponse(deps, { ...validRequest, timestampUnixSeconds: 1_000_000 - 100 }),
    ).rejects.toMatchObject({ code: "time_skew" } satisfies Partial<AuthError>);
  });

  it("rejects unknown client_id", async () => {
    const deps = makeDeps({}, null);
    await expect(handleChallengeResponse(deps, validRequest)).rejects.toMatchObject({ code: "unknown_client" });
  });

  it("rejects a banned client and does NOT consume the nonce", async () => {
    const deps = makeDeps({}, makeClient({ isBanned: true }));
    await expect(handleChallengeResponse(deps, validRequest)).rejects.toMatchObject({ code: "denied" });
    expect(deps.nonceStore.consumeNonce).not.toHaveBeenCalled();
  });

  it("rejects a client over quota", async () => {
    const deps = makeDeps({}, makeClient({ quotaLimitBytes: 100, bytesUsed: 100 }));
    await expect(handleChallengeResponse(deps, validRequest)).rejects.toMatchObject({ code: "denied" });
  });

  it("rejects a replayed nonce", async () => {
    const deps = makeDeps({
      nonceStore: {
        issueNonce: vi.fn(),
        consumeNonce: vi.fn().mockResolvedValue(false), // уже использован
      },
    });
    await expect(handleChallengeResponse(deps, validRequest)).rejects.toMatchObject({ code: "replay" });
  });

  it("rejects an invalid signature and does not issue a session", async () => {
    const deps = makeDeps({
      verifier: { verify: vi.fn().mockResolvedValue(false) },
    });
    await expect(handleChallengeResponse(deps, validRequest)).rejects.toMatchObject({ code: "bad_signature" });
    expect(deps.sessionStore.save).not.toHaveBeenCalled();
  });

  it("signs over exactly `${nonce}${timestamp}`, matching the Go client (core/internal/adapters/auth/http_challenge.go)", async () => {
    const deps = makeDeps();
    await handleChallengeResponse(deps, validRequest);

    const verifyMock = deps.verifier.verify as ReturnType<typeof vi.fn>;
    const [, messageArg] = verifyMock.mock.calls[0]!;
    const messageText = new TextDecoder().decode(messageArg as Uint8Array);
    expect(messageText).toBe(`${validRequest.nonce}${validRequest.timestampUnixSeconds}`);
  });
});
