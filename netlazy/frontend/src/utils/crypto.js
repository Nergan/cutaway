/**
 * Core cryptography & identity utilities.
 * Hybrid PQ (Ed25519 + ML-DSA-65). Both private keys are derived from a
 * single random master seed and kept encrypted-at-rest in IndexedDB under
 * a non-extractable AES-GCM wrapping key. The master seed itself is never
 * persisted anywhere: it lives in memory only long enough to derive the
 * two sub-keys and to be shown to the user once, as a BIP-39 recovery
 * phrase, immediately after generation.
 */

import { ed25519 } from '@noble/curves/ed25519';
import { entropyToMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english';

const DB_NAME = 'netlazy_pq_vault';
const STORE_NAME = 'keys';

function openDB() {
    return new Promise((resolve, reject) => {
        try {
            const req = indexedDB.open(DB_NAME, 1);
            req.onupgradeneeded = (e) => {
                e.target.result.createObjectStore(STORE_NAME);
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        } catch (e) {
            reject(e);
        }
    });
}

async function setItem(key, value) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function getItem(key) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).get(key);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

export async function clearIdentity() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

export async function hasHybridKeys() {
    const pub = await getItem("ed25519_pub");
    return !!pub;
}

function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}

function bufferToHex(buffer) {
    return Array.from(new Uint8Array(buffer)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function formatPEM(base64, type) {
    const lines = base64.match(/.{1,64}/g).join('\n');
    return `-----BEGIN ${type}-----\n${lines}\n-----END ${type}-----`;
}

/**
 * HKDF-SHA256 sub-seed derivation with domain separation, so the Ed25519
 * and ML-DSA keys never consume the same raw entropy directly even though
 * they both trace back to one master seed / recovery phrase.
 */
async function deriveSubSeed(masterSeed, label) {
    const ikm = await window.crypto.subtle.importKey('raw', masterSeed, 'HKDF', false, ['deriveBits']);
    const bits = await window.crypto.subtle.deriveBits(
        { name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(0), info: new TextEncoder().encode(label) },
        ikm,
        256
    );
    return new Uint8Array(bits);
}

/** Wraps a raw 32-byte Ed25519 public key into a DER SPKI ArrayBuffer via WebCrypto. */
async function ed25519PublicKeyToSpki(pubRaw) {
    const key = await window.crypto.subtle.importKey('raw', pubRaw, 'Ed25519', true, ['verify']);
    return window.crypto.subtle.exportKey('spki', key);
}

async function deriveUserId(edPubBuffer, mldsaPubRaw) {
    const combined = new Uint8Array(edPubBuffer.byteLength + mldsaPubRaw.byteLength);
    combined.set(new Uint8Array(edPubBuffer), 0);
    combined.set(new Uint8Array(mldsaPubRaw), edPubBuffer.byteLength);
    
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', combined.buffer);
    return bufferToHex(hashBuffer);
}

export async function generateIdentity() {
    // Single 256-bit root of trust. Never written to disk - lives only in
    // this function's scope until it is wiped at the very end.
    const masterSeed = window.crypto.getRandomValues(new Uint8Array(32));

    const edSeed = await deriveSubSeed(masterSeed, 'netlazy-ed25519-v1');
    const mldsaSeed = await deriveSubSeed(masterSeed, 'netlazy-mldsa65-v1');

    const edPubRaw = ed25519.getPublicKey(edSeed);
    const edPubSpki = await ed25519PublicKeyToSpki(edPubRaw);
    const edPubPem = formatPEM(arrayBufferToBase64(edPubSpki), "PUBLIC KEY");

    const { ml_dsa65 } = await import('@noble/post-quantum/ml-dsa');
    const mldsaKeys = ml_dsa65.keygen(mldsaSeed);
    const mldsaPubHex = bufferToHex(mldsaKeys.publicKey);

    const wrapKey = await window.crypto.subtle.generateKey(
        { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]
    );

    const edIv = window.crypto.getRandomValues(new Uint8Array(12));
    const edPrivEnc = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv: edIv }, wrapKey, edSeed
    );

    const mldsaIv = window.crypto.getRandomValues(new Uint8Array(12));
    const mldsaPrivEnc = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv: mldsaIv }, wrapKey, mldsaKeys.secretKey
    );

    await setItem("aes_wrap_key", wrapKey);
    await setItem("ed25519_iv", edIv);
    await setItem("ed25519_priv_enc", edPrivEnc);
    await setItem("ed25519_pub", edPubPem);
    await setItem("mldsa_iv", mldsaIv);
    await setItem("mldsa_priv_enc", mldsaPrivEnc);
    await setItem("mldsa_pub", mldsaPubHex);

    const userId = await deriveUserId(edPubSpki, mldsaKeys.publicKey);

    // Human-readable, checksummed, one-time-reveal backup of masterSeed.
    // The caller is responsible for displaying it exactly once and never
    // persisting it (see IdentityBackupModal.vue).
    const recoveryPhrase = entropyToMnemonic(masterSeed, wordlist);

    edSeed.fill(0);
    mldsaSeed.fill(0);
    mldsaKeys.secretKey.fill(0);
    masterSeed.fill(0);

    return { userId, edPubPem, mldsaPubHex, recoveryPhrase };
}

export async function signMigrationPayload(legacyPrivPem, newEdPem, newMldsaHex, timestamp) {
    const pemHeader = "-----BEGIN PRIVATE KEY-----";
    const pemFooter = "-----END PRIVATE KEY-----";
    const rsaHeader = "-----BEGIN RSA PRIVATE KEY-----";
    const rsaFooter = "-----END RSA PRIVATE KEY-----";
    
    let b64 = legacyPrivPem;
    if (b64.includes(pemHeader)) {
        b64 = b64.replace(pemHeader, "").replace(pemFooter, "").replace(/\s/g, "");
    } else {
        b64 = b64.replace(rsaHeader, "").replace(rsaFooter, "").replace(/\s/g, "");
    }
    
    const binaryDer = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    
    const key = await window.crypto.subtle.importKey(
        "pkcs8",
        binaryDer.buffer,
        { name: "RSA-PSS", hash: "SHA-256" },
        true,
        ["sign"]
    );
    
    const spki = await window.crypto.subtle.exportKey("spki", key);
    const pubB64 = arrayBufferToBase64(spki);
    const pubPem = `-----BEGIN PUBLIC KEY-----\n${pubB64.match(/.{1,64}/g).join('\n')}\n-----END PUBLIC KEY-----`;
    
    const payloadStr = `PQDA-MIGRATE-v1\n${newEdPem}\n${newMldsaHex}\n${timestamp}`;
    const payload = new TextEncoder().encode(payloadStr);
    
    const signature = await window.crypto.subtle.sign({ name: "RSA-PSS", saltLength: 32 }, key, payload);
    
    return {
        signatureB64: arrayBufferToBase64(signature),
        pubPem: pubPem
    };
}

export async function signHybridPayload(payloadString) {
    const wrapKey = await getItem("aes_wrap_key");
    const edIv = await getItem("ed25519_iv");
    const edPrivEnc = await getItem("ed25519_priv_enc");
    const mldsaIv = await getItem("mldsa_iv");
    const mldsaPrivEnc = await getItem("mldsa_priv_enc");

    if (!wrapKey || !edIv || !edPrivEnc || !mldsaIv || !mldsaPrivEnc) {
        throw new Error("Missing keys in vault");
    }

    const data = new TextEncoder().encode(payloadString);

    const edPrivRaw = await window.crypto.subtle.decrypt({ name: "AES-GCM", iv: edIv }, wrapKey, edPrivEnc);
    const edSeed = new Uint8Array(edPrivRaw);
    const edSig = arrayBufferToBase64(ed25519.sign(data, edSeed));
    edSeed.fill(0);

    const mldsaPrivRaw = await window.crypto.subtle.decrypt({ name: "AES-GCM", iv: mldsaIv }, wrapKey, mldsaPrivEnc);
    const mldsaPriv = new Uint8Array(mldsaPrivRaw);
    
    const { ml_dsa65 } = await import('@noble/post-quantum/ml-dsa');
    const pqSigBuffer = ml_dsa65.sign(mldsaPriv, data);
    const pqSig = arrayBufferToBase64(pqSigBuffer);
    
    mldsaPriv.fill(0);

    return { edSig, pqSig };
}

export async function signIdentityPayload(method, path, timestamp, nonce, bodyHash) {
    const canonical = `PQDA-ANCHOR-v1\n${method}\n${path}\n${timestamp}\n${nonce}\n${bodyHash}`;
    return await signHybridPayload(canonical);
}

export function solvePoW(challengeId, difficulty) {
    return new Promise((resolve, reject) => {
        const workerCode = `
            async function sha256Hex(buffer) {
                const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
                const arr = Array.from(new Uint8Array(hashBuffer));
                return arr.map(b => b.toString(16).padStart(2, '0')).join('');
            }
            self.onmessage = async (e) => {
                const { challengeId, difficulty } = e.data;
                const prefix = "0".repeat(difficulty);
                let nonce = 0;
                const encoder = new TextEncoder();
                while (true) {
                    const data = encoder.encode(challengeId + nonce.toString());
                    const hash = await sha256Hex(data);
                    if (hash.startsWith(prefix)) {
                        self.postMessage(nonce.toString());
                        return;
                    }
                    nonce++;
                }
            };
        `;
        const blob = new Blob([workerCode], { type: 'application/javascript' });
        const worker = new Worker(URL.createObjectURL(blob));
        worker.onmessage = (e) => {
            worker.terminate();
            resolve(e.data);
        };
        worker.onerror = (e) => {
            worker.terminate();
            reject(e);
        };
        worker.postMessage({ challengeId, difficulty });
    });
}

let cachedFingerprint = null;
export async function getFingerprint() {
    if (cachedFingerprint) return cachedFingerprint;

    const components = [];
    components.push(Intl.DateTimeFormat().resolvedOptions().timeZone);
    components.push(navigator.language);
    components.push(`${window.screen.width}x${window.screen.height}x${window.screen.colorDepth}`);
    
    try {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        ctx.textBaseline = "top";
        ctx.font = "14px 'Arial'";
        ctx.textBaseline = "alphabetic";
        ctx.fillStyle = "#f60";
        ctx.fillRect(125, 1, 62, 20);
        ctx.fillStyle = "#069";
        ctx.fillText("netlazy", 2, 15);
        ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
        ctx.fillText("netlazy", 4, 17);
        components.push(canvas.toDataURL());
    } catch (e) {
        components.push("canvas_error");
    }

    const encoder = new TextEncoder();
    const data = encoder.encode(components.join("||"));
    cachedFingerprint = await deriveHexHash(data);
    return cachedFingerprint;
}

async function deriveHexHash(data) {
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
    return bufferToHex(hashBuffer);
}

export async function hashBody(bodyStringOrBuffer) {
    const encoder = new TextEncoder();
    const data = typeof bodyStringOrBuffer === 'string' ? encoder.encode(bodyStringOrBuffer) : bodyStringOrBuffer;
    return await deriveHexHash(data);
}