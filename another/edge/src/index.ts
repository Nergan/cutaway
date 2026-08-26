import type { Env } from "./env.js";
import type { ChallengeResponseDeps } from "./domain/challenge_response_service.js";
import { handleNonce } from "./handlers/nonce.js";
import { handleAuth } from "./handlers/auth.js";
import { handleEnroll } from "./handlers/enroll.js";
import { handleProxy } from "./handlers/proxy.js";
import { DurableObjectNonceStore, NonceLedgerObject } from "./adapters/durable_object_nonce_store.js";
import { RestProxyUserRepository } from "./adapters/rest_proxy_user_repository.js";
import { WebCryptoEd25519Verifier } from "./adapters/webcrypto_ed25519_verifier.js";
import { KvBanCache } from "./adapters/kv_ban_cache.js";
import { KvSessionStore } from "./adapters/kv_session_store.js";
import { SystemClock } from "./adapters/system_clock.js";
import { generateSessionToken } from "./adapters/session_token.js";
import { runPinger } from "./adapters/pinger.js";
import { clientIp, closeOriginSession, hashIp, reportAuthOutcome } from "./adapters/session_reporter.js";

export { NonceLedgerObject };

function secretsEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let acc = 0;
  for (let i = 0; i < a.length; i++) acc |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return acc === 0;
}

function buildUserRepo(env: Env): RestProxyUserRepository {
  return new RestProxyUserRepository({
    baseUrl: env.MONGO_REST_PROXY_URL,
    secret: env.ANOTHER_SERVICE_SECRET,
  });
}

function buildChallengeResponseDeps(env: Env): ChallengeResponseDeps {
  return {
    nonceStore: new DurableObjectNonceStore(env.NONCE_LEDGER),
    userRepo: buildUserRepo(env),
    verifier: new WebCryptoEd25519Verifier(),
    clock: new SystemClock(),
    banCache: new KvBanCache(env.BAN_CACHE),
    sessionStore: new KvSessionStore(env.BAN_CACHE),
    generateSessionToken,
  };
}

async function handleBanInvalidate(request: Request, env: Env): Promise<Response> {
  const secret = request.headers.get("X-Another-Proxy-Secret") ?? "";
  if (!secretsEqual(secret, env.ANOTHER_SERVICE_SECRET)) {
    return new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 });
  }
  let body: { client_id?: string };
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid JSON body" }), { status: 400 });
  }
  if (!body.client_id) {
    return new Response(JSON.stringify({ error: "client_id required" }), { status: 400 });
  }
  await new KvBanCache(env.BAN_CACHE).invalidate(body.client_id);
  return Response.json({ ok: true });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    try {
      switch (url.pathname) {
        case "/health": {
          if (request.method !== "GET") return methodNotAllowed();
          return Response.json({ status: "ok", service: "another-edge" });
        }

        case "/nonce": {
          if (request.method !== "GET") return methodNotAllowed();
          const deps = buildChallengeResponseDeps(env);
          return handleNonce(deps.nonceStore);
        }

        case "/auth": {
          if (request.method !== "POST") return methodNotAllowed();
          const peek = request.clone();
          const deps = buildChallengeResponseDeps(env);
          const response = await handleAuth(request, deps);
          ctx.waitUntil(reportAuthOutcome(env, peek, response, request));
          return response;
        }

        case "/enroll": {
          if (request.method !== "POST") return methodNotAllowed();
          return handleEnroll(request, {
            userRepo: buildUserRepo(env),
            clock: new SystemClock(),
            nodesJson: env.NODES_JSON,
          });
        }

        case "/internal/ban-invalidate": {
          if (request.method !== "POST") return methodNotAllowed();
          return handleBanInvalidate(request, env);
        }

        case "/proxy": {
          const ip = clientIp(request);
          const ipHashP = hashIp(ip, env.ANOTHER_SERVICE_SECRET);
          return handleProxy(request, {
            sessionStore: new KvSessionStore(env.BAN_CACHE),
            userRepo: buildUserRepo(env),
            ctx,
            onFinished: (clientId, bytes) => {
              ctx.waitUntil(
                ipHashP.then((ipHash) =>
                  closeOriginSession(env, { clientId, ipHash, bytesDelta: bytes }),
                ),
              );
            },
          });
        }

        default: {
          if (url.pathname === "/xhttp" || url.pathname.startsWith("/xhttp/")) {
            return proxyXHTTP(request, env);
          }
          return new Response("not found", { status: 404 });
        }
      }
    } catch (err) {
      console.error("unhandled error", err);
      return new Response(JSON.stringify({ error: "internal server error" }), { status: 500 });
    }
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runPinger(env));
  },
} satisfies ExportedHandler<Env>;

function methodNotAllowed(): Response {
  return new Response(JSON.stringify({ error: "method not allowed" }), { status: 405 });
}

async function proxyXHTTP(request: Request, env: Env): Promise<Response> {
  const origin = (env.ORIGIN_XHTTP_URL || env.MONGO_REST_PROXY_URL || "").replace(/\/$/, "");
  if (!origin) {
    return new Response(JSON.stringify({ error: "xhttp origin not configured" }), { status: 501 });
  }
  const incoming = new URL(request.url);
  const target = `${origin}${incoming.pathname}${incoming.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  return fetch(target, {
    method: request.method,
    headers,
    body: request.body,
    redirect: "manual",
  });
}
