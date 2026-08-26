import type { SignatureVerifierPort } from "../ports/signature_verifier_port.js";

function hexToBytes(hex: string): Uint8Array {
  if (hex.length % 2 !== 0) {
    throw new Error(`invalid hex string length: ${hex.length}`);
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

/**
 * WebCryptoEd25519Verifier — верификация подписи через нативный
 * `crypto.subtle` рантайма Cloudflare Workers. Ed25519 поддерживается
 * Workers нативно (алгоритм `{name: "Ed25519"}`) без флага
 * nodejs_compat и без внешней npm-зависимости.
 */
export class WebCryptoEd25519Verifier implements SignatureVerifierPort {
  async verify(publicKeyHex: string, message: Uint8Array, signatureHex: string): Promise<boolean> {
    let publicKeyBytes: Uint8Array;
    let signatureBytes: Uint8Array;
    try {
      publicKeyBytes = hexToBytes(publicKeyHex);
      signatureBytes = hexToBytes(signatureHex);
    } catch {
      return false; // некорректный hex — считаем подпись невалидной, не бросаем исключение
    }

    if (publicKeyBytes.length !== 32 || signatureBytes.length !== 64) {
      return false; // Ed25519: публичный ключ 32 байта, подпись 64 байта
    }

    let cryptoKey: CryptoKey;
    try {
      cryptoKey = await crypto.subtle.importKey(
        "raw",
        publicKeyBytes,
        { name: "Ed25519" },
        false,
        ["verify"],
      );
    } catch {
      return false; // невалидный публичный ключ
    }

    return crypto.subtle.verify("Ed25519", cryptoKey, signatureBytes, message);
  }
}
