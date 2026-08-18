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

function base64ToArrayBuffer(base64) {
    const binary = window.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

function bufferToHex(buffer) {
    return Array.from(new Uint8Array(buffer)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function formatPEM(base64, type) {
    const lines = base64.match(/.{1,64}/g).join('\n');
    return `-----BEGIN ${type}-----\n${lines}\n-----END ${type}-----`;
}

function stripPEM(pem) {
    return pem.replace(/-----BEGIN [^-]+-----/g, '')
              .replace(/-----END [^-]+-----/g, '')
              .replace(/\s+/g, '');
}

function extractSpkiFromPkcs8(derBytes) {
    const bytes = new Uint8Array(derBytes);
    for (let i = 0; i < bytes.length - 10; i++) {
        if (bytes[i] === 0x02 && bytes[i+1] === 0x01 && bytes[i+2] === 0x00 && bytes[i+3] === 0x02 && bytes[i+4] === 0x82) {
            const nLen = (bytes[i+5] << 8) | bytes[i+6];
            const eTag = i + 7 + nLen;
            if (bytes[eTag] === 0x02) {
                const eLen = bytes[eTag+1];
                const n = bytes.slice(i+3, eTag);
                const e = bytes.slice(eTag, eTag+2+eLen);
                
                const rsaPubLen = n.length + e.length;
                const rsaPubSeq = new Uint8Array(4 + rsaPubLen);
                rsaPubSeq.set([0x30, 0x82, (rsaPubLen>>8)&0xFF, rsaPubLen&0xFF], 0);
                rsaPubSeq.set(n, 4);
                rsaPubSeq.set(e, 4 + n.length);
                
                const algoId = new Uint8Array([0x30, 0x0D, 0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01, 0x05, 0x00]);
                const bitStringLen = rsaPubSeq.length + 1;
                const bitString = new Uint8Array(4 + bitStringLen);
                bitString.set([0x03, 0x82, (bitStringLen>>8)&0xFF, bitStringLen&0xFF, 0x00], 0);
                bitString.set(rsaPubSeq, 5);
                
                const spkiLen = algoId.length + bitString.length;
                const spkiSeq = new Uint8Array(4 + spkiLen);
                spkiSeq.set([0x30, 0x82, (spkiLen>>8)&0xFF, spkiLen&0xFF], 0);
                spkiSeq.set(algoId, 4);
                spkiSeq.set(bitString, 4 + algoId.length);
                return spkiSeq.buffer;
            }
        }
    }
    throw new Error("Invalid RSA PKCS#8 key format");
}

async function sha256Hex(buffer) {
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', buffer);
    return bufferToHex(hashBuffer);
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

export async function signLegacyMigration(legacyPem, newEdPubPem, newMldsaHex, timestamp) {
    const payload = `MIGRATE\n${newEdPubPem}\n${newMldsaHex}\n${timestamp}`;
    
    const base64 = stripPEM(legacyPem);
    const buffer = base64ToArrayBuffer(base64);
    
    const spkiBuffer = extractSpkiFromPkcs8(buffer);
    const spkiPem = formatPEM(arrayBufferToBase64(spkiBuffer), "PUBLIC KEY");

    const privateKey = await window.crypto.subtle.importKey(
        "pkcs8", buffer, { name: "RSA-PSS", hash: "SHA-256" }, true, ["sign"]
    );

    const data = new TextEncoder().encode(payload);
    const signatureBuffer = await window.crypto.subtle.sign(
        { name: "RSA-PSS", saltLength: 32 }, privateKey, data
    );
    
    return { 
        signature: arrayBufferToBase64(signatureBuffer),
        publicPem: spkiPem
    };
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
    cachedFingerprint = await sha256Hex(data);
    return cachedFingerprint;
}

export async function hashBody(bodyStringOrBuffer) {
    const encoder = new TextEncoder();
    const data = typeof bodyStringOrBuffer === 'string' ? encoder.encode(bodyStringOrBuffer) : bodyStringOrBuffer;
    return await sha256Hex(data);
}