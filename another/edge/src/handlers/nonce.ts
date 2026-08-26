import type { NonceStorePort } from "../ports/nonce_store_port.js";

/** handleNonce — GET /nonce (§7.2, первый шаг challenge-response). */
export async function handleNonce(nonceStore: NonceStorePort): Promise<Response> {
  const nonce = await nonceStore.issueNonce();
  return Response.json({ nonce });
}
