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

  let nodes: unknown;
  try {
    nodes = JSON.parse(deps.nodesJson);
  } catch {
    nodes = [];
  }

  return Response.json({
    ok: true,
    client_id: enrollment.clientId,
    vless_user_id: vlessUserIdHex,
    nodes,
  });
}
