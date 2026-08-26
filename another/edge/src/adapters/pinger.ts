import type { Env } from "../env.js";

export interface PingTarget {
  name: string;
  url: string;
  interval_s: number;
  expect_status: number;
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

export async function postWorkerEvent(
  env: Env,
  category: string,
  detail: Record<string, unknown> = {},
  clientId?: string,
): Promise<void> {
  try {
    await fetch(`${proxyBase(env)}/internal/v1/events`, {
      method: "POST",
      headers: proxyHeaders(env),
      body: JSON.stringify({
        category,
        client_id: clientId ?? null,
        detail,
      }),
    });
  } catch (err) {
    console.error("postWorkerEvent failed", err);
  }
}

/**
 * Pinger: Cloudflare Cron читает список URL из origin API (админка его
 * редактирует), без хардкода Render. См. docs/observability.md.
 */
export async function runPinger(env: Env): Promise<void> {
  const res = await fetch(`${proxyBase(env)}/internal/v1/ping-targets`, {
    method: "GET",
    headers: proxyHeaders(env),
  });
  if (!res.ok) {
    console.error("ping-targets fetch failed", res.status);
    return;
  }
  const payload = (await res.json()) as { targets?: PingTarget[] };
  const targets = payload.targets ?? [];

  for (const target of targets) {
    const started = Date.now();
    try {
      const pingRes = await fetch(target.url, { method: "GET", redirect: "manual" });
      const elapsedMs = Date.now() - started;
      const ok = pingRes.status === target.expect_status;
      await postWorkerEvent(env, ok ? "ping_ok" : "ping_fail", {
        name: target.name,
        url: target.url,
        status: pingRes.status,
        elapsed_ms: elapsedMs,
      });
    } catch (err) {
      await postWorkerEvent(env, "ping_fail", {
        name: target.name,
        url: target.url,
        error: err instanceof Error ? err.message : "ping error",
      });
    }
  }
}
