import type { Env } from "../env.js";
import { postWorkerEvent } from "./pinger.js";

const HASH_HEX_LEN = 16;

export function clientIp(request: Request): string {
  const cf = request.headers.get("CF-Connecting-IP");
  if (cf && cf.trim()) return cf.trim();
  const forwarded = request.headers.get("X-Forwarded-For");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return "";
}

export async function hashIp(ip: string, secret: string): Promise<string> {
  const material = `${ip}|${secret}`;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(material));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, HASH_HEX_LEN);
}

function proxyHeaders(env: Env): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Another-Proxy-Secret": env.ANOTHER_SERVICE_SECRET,
  };
}

function proxyBase(env: Env): string {
  return env.MONGO_REST_PROXY_URL.replace(/\/$/, "");
}

export async function upsertOriginSession(
  env: Env,
  params: {
    clientId: string;
    ipHash: string;
    ip?: string;
    node?: string;
    entrypoint?: string;
    bytesDelta?: number;
  },
): Promise<void> {
  try {
    await fetch(`${proxyBase(env)}/internal/v1/sessions/upsert`, {
      method: "POST",
      headers: proxyHeaders(env),
      body: JSON.stringify({
        client_id: params.clientId,
        ip_hash: params.ipHash,
        ip: params.ip ?? null,
        node: params.node ?? "cf-worker",
        entrypoint: params.entrypoint ?? "/auth",
        bytes_delta: params.bytesDelta ?? 0,
      }),
    });
  } catch (err) {
    console.error("upsertOriginSession failed", err);
  }
}

export async function closeOriginSession(
  env: Env,
  params: { clientId: string; ipHash: string; bytesDelta?: number },
): Promise<void> {
  try {
    await fetch(`${proxyBase(env)}/internal/v1/sessions/close`, {
      method: "POST",
      headers: proxyHeaders(env),
      body: JSON.stringify({
        client_id: params.clientId,
        ip_hash: params.ipHash,
        bytes_delta: params.bytesDelta ?? 0,
      }),
    });
  } catch (err) {
    console.error("closeOriginSession failed", err);
  }
}

export async function reportAuthOutcome(
  env: Env,
  peek: Request,
  response: Response,
  original: Request,
): Promise<void> {
  let clientId: string | undefined;
  try {
    const body = (await peek.json()) as { client_id?: string };
    if (body.client_id) clientId = body.client_id;
  } catch {
    /* тело уже битое — handleAuth вернул 400 */
  }
  const ip = clientIp(original);
  const ipHash = await hashIp(ip, env.ANOTHER_SERVICE_SECRET);
  const includeRaw = env.ANOTHER_INVESTIGATION === "1";

  if (response.status >= 400 && response.status < 500) {
    await postWorkerEvent(
      env,
      "auth_fail",
      { path: "/auth", status: response.status },
      clientId,
    );
    return;
  }
  if (response.status === 200 && clientId) {
    await postWorkerEvent(env, "auth_ok", { path: "/auth" }, clientId);
    await upsertOriginSession(env, {
      clientId,
      ipHash,
      ip: includeRaw && ip ? ip : undefined,
      node: "cf-worker",
      entrypoint: "/auth",
    });
  }
}
