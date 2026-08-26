import { AuthError, handleChallengeResponse, type ChallengeResponseDeps } from "../domain/challenge_response_service.js";

interface AuthRequestBody {
  client_id?: string;
  signature?: string;
  timestamp?: number;
  nonce?: string;
}

/**
 * handleAuth — POST /auth (§7.2, второй шаг). Тонкий HTTP-адаптер поверх
 * domain.handleChallengeResponse: парсинг запроса, маппинг ошибок на
 * HTTP-статусы, сериализация ответа. Вся содержательная логика — в
 * domain-слое и не зависит от того, что транспорт именно HTTP.
 */
export async function handleAuth(request: Request, deps: ChallengeResponseDeps): Promise<Response> {
  let body: AuthRequestBody;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid JSON body" }), { status: 400 });
  }

  if (!body.client_id || !body.signature || !body.timestamp || !body.nonce) {
    return new Response(
      JSON.stringify({ error: "missing required fields: client_id, signature, timestamp, nonce" }),
      { status: 400 },
    );
  }

  try {
    const result = await handleChallengeResponse(deps, {
      clientId: body.client_id,
      signatureHex: body.signature,
      timestampUnixSeconds: body.timestamp,
      nonce: body.nonce,
    });
    return Response.json({
      session_token: result.sessionToken,
      vless_user_id: result.vlessUserIdHex,
    });
  } catch (err) {
    if (err instanceof AuthError) {
      // 403 для всех вариантов отказа — не различаем причину в HTTP-ответе
      // клиенту (unknown_client vs bad_signature vs replay), чтобы не давать
      // атакующему лишней информации для перебора client_id/подписи.
      // Точная причина остаётся в server-side логах (см. index.ts).
      return new Response(JSON.stringify({ error: "authentication failed" }), { status: 403 });
    }
    throw err;
  }
}
