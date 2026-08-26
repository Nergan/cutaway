import type { UserRepositoryPort } from "../ports/user_repository_port.js";
import type { ClockPort } from "../ports/clock_port.js";

interface EnrollRequestBody {
  enrollment_token?: string;
  public_key?: string; // hex, 32 байта Ed25519
  public_key_mldsa65?: string; // hex ML-DSA-65, опционально до PQ на Worker
}

export interface EnrollDeps {
  userRepo: UserRepositoryPort;
  clock: ClockPort;
  nodesJson: string; // см. Env.NODES_JSON
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * resolveNodes — подставляет в узлы собственный адрес воркера.
 *
 * NODES_JSON хранится в wrangler.toml, где реальный хост воркера неизвестен:
 * он зависит от аккаунта (`<name>.<subdomain>.workers.dev`), а позже может
 * стать кастомным доменом. Захардкоженный хост в конфиге неизбежно расходится
 * с фактическим деплоем, а клиент из-за этого стучится в несуществующее имя.
 * Поэтому: узел может не задавать `host` и `control_plane` — тогда они берутся
 * из URL текущего запроса, то есть ровно того адреса, по которому клиент только
 * что успешно дошёл до /enroll.
 *
 * `control_plane` подставляется всем узлам без него: challenge-response
 * (/nonce + /auth) всегда живёт на воркере, независимо от того, через какой
 * узел пойдёт трафик. Без этого поля Go-клиент не может авторизоваться
 * (core/internal/domain/node.go, поле ControlPlane).
 */
function resolveNodes(nodesJson: string, requestUrl: string): unknown[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(nodesJson);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];

  const self = new URL(requestUrl);
  const selfOrigin = `${self.protocol}//${self.host}`;

  return parsed.map((node) => {
    if (typeof node !== "object" || node === null) return node;
    const fields = node as Record<string, unknown>;
    const host = typeof fields.host === "string" ? fields.host : "";
    const controlPlane = typeof fields.control_plane === "string" ? fields.control_plane : "";
    return {
      ...fields,
      host: host.length > 0 ? host : self.host,
      control_plane: controlPlane.length > 0 ? controlPlane : selfOrigin,
    };
  });
}

function generateVlessUserId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * handleEnroll — POST /enroll. Реализует онбординг устройства (§7.1
 * спецификации, отсутствовавший в исходном черновике — без него схема БД
 * с полем `public_key` была нереализуема, т.к. непонятно, как оно туда
 * попадает). Одноразовый enrollment_token выдаёт администратор через
 * control-plane-admin (Part 3), устройство обменивает его на привязку
 * своего публичного ключа.
 */
export async function handleEnroll(request: Request, deps: EnrollDeps): Promise<Response> {
  let body: EnrollRequestBody;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid JSON body" }), { status: 400 });
  }

  if (!body.enrollment_token || !body.public_key) {
    return new Response(
      JSON.stringify({ error: "missing required fields: enrollment_token, public_key" }),
      { status: 400 },
    );
  }

  if (!/^[0-9a-f]{64}$/i.test(body.public_key)) {
    return new Response(JSON.stringify({ error: "public_key must be 32-byte hex (Ed25519)" }), {
      status: 400,
    });
  }

  const tokenHash = await sha256Hex(body.enrollment_token);
  const enrollment = await deps.userRepo.findEnrollmentByTokenHash(tokenHash);
  if (!enrollment) {
    return new Response(JSON.stringify({ error: "invalid or already-used enrollment token" }), {
      status: 403,
    });
  }
  if (enrollment.expiresAtUnixSeconds < deps.clock.nowUnixSeconds()) {
    return new Response(JSON.stringify({ error: "enrollment token expired" }), { status: 403 });
  }

  const vlessUserIdHex = generateVlessUserId();
  await deps.userRepo.bindDeviceIdentity(
    enrollment.clientId,
    body.public_key,
    vlessUserIdHex,
    body.public_key_mldsa65,
  );
  await deps.userRepo.consumeEnrollmentToken(tokenHash);

  return Response.json({
    ok: true,
    client_id: enrollment.clientId,
    vless_user_id: vlessUserIdHex,
    nodes: resolveNodes(deps.nodesJson, request.url),
  });
}
