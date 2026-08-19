/**
 * Core cryptography & identity utilities.
 * Hybrid PQ (Ed25519 + ML-DSA-65). Keys are device-bound in IndexedDB.
 */

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

async function deriveUserId(edPubBuffer, mldsaPubRaw) {
    const combined = new Uint8Array(edPubBuffer.byteLength + mldsaPubRaw.byteLength);
    combined.set(new Uint8Array(edPubBuffer), 0);
    combined.set(new Uint8Array(mldsaPubRaw), edPubBuffer.byteLength);
    
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', combined.buffer);
    return bufferToHex(hashBuffer);
}

export async function generateIdentity() {
    const edKeyPair = await window.crypto.subtle.generateKey(
        "Ed25519", false, ["sign", "verify"]
    );
    const edPubBuffer = await window.crypto.subtle.exportKey("spki", edKeyPair.publicKey);
    const edPubPem = formatPEM(arrayBufferToBase64(edPubBuffer), "PUBLIC KEY");

    const wrapKey = await window.crypto.subtle.generateKey(
        { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]
    );

    const { ml_dsa65 } = await import('@noble/post-quantum/ml-dsa');
    const seed = window.crypto.getRandomValues(new Uint8Array(32));
    const mldsaKeys = ml_dsa65.keygen(seed);
    const mldsaPubHex = bufferToHex(mldsaKeys.publicKey);

    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const mldsaPrivEnc = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv }, wrapKey, mldsaKeys.secretKey
    );

    await setItem("ed25519_priv", edKeyPair.privateKey);
    await setItem("ed25519_pub", edPubPem);
    await setItem("aes_wrap_key", wrapKey);
    await setItem("mldsa_iv", iv);
    await setItem("mldsa_priv_enc", mldsaPrivEnc);
    await setItem("mldsa_pub", mldsaPubHex);

    const userId = await deriveUserId(edPubBuffer, mldsaKeys.publicKey);

    mldsaKeys.secretKey.fill(0);

    return { userId, edPubPem, mldsaPubHex };
}

export async function signHybridPayload(payloadString) {
    const edPriv = await getItem("ed25519_priv");
    const wrapKey = await getItem("aes_wrap_key");
    const mldsaIv = await getItem("mldsa_iv");
    const mldsaPrivEnc = await getItem("mldsa_priv_enc");

    if (!edPriv || !wrapKey || !mldsaIv || !mldsaPrivEnc) {
        throw new Error("Missing keys in vault");
    }

    const data = new TextEncoder().encode(payloadString);

    const edSigBuffer = await window.crypto.subtle.sign("Ed25519", edPriv, data);
    const edSig = arrayBufferToBase64(edSigBuffer);

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