import { describe, it, expect } from "vitest";
import { generateKeyPairSync, sign as nodeSign } from "node:crypto";
import { WebCryptoEd25519Verifier } from "../src/adapters/webcrypto_ed25519_verifier.js";

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Извлекает сырые 32 байта публичного ключа Ed25519 из SPKI DER (Node
 * отдаёт ключи в DER по умолчанию для node:crypto; raw-формат — последние
 * 32 байта SPKI-обёртки для Ed25519, т.к. префикс OID фиксированной длины). */
function rawPublicKeyFromSpki(spki: Buffer): Uint8Array {
  return new Uint8Array(spki.subarray(spki.length - 32));
}

function rawPrivateSeedFromPkcs8(pkcs8: Buffer): Uint8Array {
  // PKCS8 Ed25519: последние 32 байта — seed приватного ключа.
  return new Uint8Array(pkcs8.subarray(pkcs8.length - 32));
}

describe("WebCryptoEd25519Verifier", () => {
  it("verifies a signature produced by node:crypto's Ed25519", async () => {
    const { publicKey, privateKey } = generateKeyPairSync("ed25519");
    const publicKeyHex = bytesToHex(rawPublicKeyFromSpki(publicKey.export({ type: "spki", format: "der" })));

    const message = new TextEncoder().encode("deadbeefcafef00d1735000000");
    const signature = nodeSign(null, message, privateKey);
    const signatureHex = bytesToHex(new Uint8Array(signature));

    const verifier = new WebCryptoEd25519Verifier();
    const ok = await verifier.verify(publicKeyHex, message, signatureHex);
    expect(ok).toBe(true);
  });

  it("rejects a signature for tampered data", async () => {
    const { publicKey, privateKey } = generateKeyPairSync("ed25519");
    const publicKeyHex = bytesToHex(rawPublicKeyFromSpki(publicKey.export({ type: "spki", format: "der" })));

    const message = new TextEncoder().encode("original-message");
    const signature = nodeSign(null, message, privateKey);
    const signatureHex = bytesToHex(new Uint8Array(signature));

    const verifier = new WebCryptoEd25519Verifier();
    const tampered = new TextEncoder().encode("tampered-message");
    const ok = await verifier.verify(publicKeyHex, tampered, signatureHex);
    expect(ok).toBe(false);
  });

  it("rejects a signature verified against the wrong public key", async () => {
    const pairA = generateKeyPairSync("ed25519");
    const pairB = generateKeyPairSync("ed25519");
    const wrongPublicKeyHex = bytesToHex(rawPublicKeyFromSpki(pairB.publicKey.export({ type: "spki", format: "der" })));

    const message = new TextEncoder().encode("some message");
    const signature = nodeSign(null, message, pairA.privateKey);
    const signatureHex = bytesToHex(new Uint8Array(signature));

    const verifier = new WebCryptoEd25519Verifier();
    const ok = await verifier.verify(wrongPublicKeyHex, message, signatureHex);
    expect(ok).toBe(false);
  });

  it("rejects malformed hex without throwing", async () => {
    const verifier = new WebCryptoEd25519Verifier();
    const ok = await verifier.verify("not-hex!!", new TextEncoder().encode("x"), "also-not-hex");
    expect(ok).toBe(false);
  });

  it("rejects keys/signatures of the wrong length", async () => {
    const verifier = new WebCryptoEd25519Verifier();
    const ok = await verifier.verify("aabb", new TextEncoder().encode("x"), "ccdd");
    expect(ok).toBe(false);
  });
});
