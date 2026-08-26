import type { NonceStorePort } from "../ports/nonce_store_port.js";
import type { UserRepositoryPort } from "../ports/user_repository_port.js";
import type { SignatureVerifierPort } from "../ports/signature_verifier_port.js";
import type { ClockPort } from "../ports/clock_port.js";
import type { BanCachePort } from "../ports/ban_cache_port.js";
import type { SessionStorePort } from "../ports/session_store_port.js";
import { isWithinSlidingWindow } from "./time_policy.js";
import { evaluateAccess } from "./ban_policy.js";

/** Срок жизни session_token — должно с запасом хватать на то, чтобы клиент
 * успел открыть WS-соединение к /proxy сразу после /auth (обычно доли
 * секунды, см. ConnectUseCase.Execute в core/). */
const SESSION_TOKEN_TTL_SECONDS = 120;

export class AuthError extends Error {
  constructor(
    message: string,
    public readonly code: "time_skew" | "denied" | "replay" | "unknown_client" | "bad_signature",
  ) {
    super(message);
    this.name = "AuthError";
  }
}

export interface ChallengeResponseDeps {
  nonceStore: NonceStorePort;
  userRepo: UserRepositoryPort;
  verifier: SignatureVerifierPort;
  clock: ClockPort;
  banCache: BanCachePort;
  sessionStore: SessionStorePort;
  /** Генератор session_token — вынесен как функция, чтобы тесты были детерминированными. */
  generateSessionToken: () => string;
}

export interface ChallengeResponseRequest {
  clientId: string;
  signatureHex: string;
  timestampUnixSeconds: number;
  nonce: string;
}

export interface ChallengeResponseResult {
  sessionToken: string;
  vlessUserIdHex: string;
}

/**
 * handleChallengeResponse — прямой перенос последовательности §7.2
 * спецификации в рабочий код:
 *   1. sliding window (±30с)
 *   2. бан/квота (cache-aside через KV, fallback на Mongo)
 *   3. anti-replay (consume nonce через Durable Object — атомарно)
 *   4. найти клиента и его public_key в Mongo
 *   5. проверить Ed25519-подпись Sign(nonce ⧺ timestamp)
 *   6. выдать session_token + vless_user_id
 *
 * Порядок шагов 2 и 3 важен: проверяем бан ДО списания nonce, чтобы
 * забаненный клиент не мог "сжигать" чужие nonce бесполезными попытками
 * (незначительная, но бесплатная защита от лишней нагрузки на Durable Object).
 */
export async function handleChallengeResponse(
  deps: ChallengeResponseDeps,
  req: ChallengeResponseRequest,
): Promise<ChallengeResponseResult> {
  if (!isWithinSlidingWindow(deps.clock.nowUnixSeconds(), req.timestampUnixSeconds)) {
    throw new AuthError("timestamp outside sliding window", "time_skew");
  }

  // Нужна запись клиента и для бан-чека (квота хранится там же), и для
  // проверки подписи — запрашиваем один раз.
  const client = await deps.userRepo.findClient(req.clientId);
  if (!client) {
    throw new AuthError(`unknown client_id ${req.clientId}`, "unknown_client");
  }

  const denied = await deps.banCache.isBanned(req.clientId, async () => {
    const decision = evaluateAccess(client);
    return !decision.allowed;
  });
  if (denied) {
    throw new AuthError("client is banned or over quota", "denied");
  }

  const nonceOk = await deps.nonceStore.consumeNonce(req.nonce);
  if (!nonceOk) {
    throw new AuthError("nonce invalid, expired, or already used", "replay");
  }

  const signPayload = new TextEncoder().encode(`${req.nonce}${req.timestampUnixSeconds}`);
  const validSignature = await deps.verifier.verify(client.publicKeyHex, signPayload, req.signatureHex);
  if (!validSignature) {
    throw new AuthError("signature verification failed", "bad_signature");
  }

  const sessionToken = deps.generateSessionToken();
  await deps.sessionStore.save(
    sessionToken,
    { clientId: client.clientId, vlessUserIdHex: client.vlessUserIdHex },
    SESSION_TOKEN_TTL_SECONDS,
  );

  return {
    sessionToken,
    vlessUserIdHex: client.vlessUserIdHex,
  };
}
