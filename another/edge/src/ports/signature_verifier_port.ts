/**
 * SignatureVerifierPort — проверка Ed25519-подписи клиента. Реализация
 * (adapters/webcrypto_ed25519_verifier.ts) использует нативный
 * `crypto.subtle` Workers-рантайма — Ed25519 в WebCrypto поддерживается в
 * Cloudflare Workers нативно (алгоритм `{name: "Ed25519"}`), внешняя
 * крипто-библиотека не нужна.
 */
export interface SignatureVerifierPort {
  verify(publicKeyHex: string, message: Uint8Array, signatureHex: string): Promise<boolean>;
}
