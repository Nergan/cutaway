/**
 * Core cryptography & identity utilities using WebCrypto API.
 */

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

function formatPEM(base64, type) {
    const lines = base64.match(/.{1,64}/g).join('\n');
    return `-----BEGIN ${type}-----\n${lines}\n-----END ${type}-----`;
}

function stripPEM(pem) {
    return pem.replace(/-----BEGIN [^-]+-----/g, '')
              .replace(/-----END [^-]+-----/g, '')
              .replace(/\s+/g, '');
}

async function sha256Hex(buffer) {
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function generateIdentity() {
    const keyPair = await window.crypto.subtle.generateKey(
        {
            name: "RSA-PSS",
            modulusLength: 2048,
            publicExponent: new Uint8Array([1, 0, 1]),
            hash: "SHA-256",
        },
        true,
        ["sign", "verify"]
    );

    const publicKeyBuffer = await window.crypto.subtle.exportKey("spki", keyPair.publicKey);
    const privateKeyBuffer = await window.crypto.subtle.exportKey("pkcs8", keyPair.privateKey);

    const publicKeyPem = formatPEM(arrayBufferToBase64(publicKeyBuffer), "PUBLIC KEY");
    const privateKeyPem = formatPEM(arrayBufferToBase64(privateKeyBuffer), "PRIVATE KEY");
    
    // Derive deterministic User ID (SHA256 of Canonical SPKI DER)
    const userId = await sha256Hex(publicKeyBuffer);

    return { publicKeyPem, privateKeyPem, userId, keyPair };
}

export async function loadPrivateKey(privateKeyPem) {
    const base64 = stripPEM(privateKeyPem);
    const buffer = base64ToArrayBuffer(base64);

    const privateKey = await window.crypto.subtle.importKey(
        "pkcs8",
        buffer,
        { name: "RSA-PSS", hash: "SHA-256" },
        true,
        ["sign"]
    );

    // To derive user_id we must extract the public key. WebCrypto doesn't allow 
    // deriving public from private natively, but we can do a standard Jwk export/import mapping
    // if needed. However, we assume we have both or can fetch it. For now, we will require the user
    // to just generate a fresh one if lost, or we implement a Jwk converter. 
    // Since plan.md states "Client extracts public key", we use an RSASSA-PKCS1-v1_5 trick via JWK:
    
    const jwk = await window.crypto.subtle.exportKey("jwk", privateKey);
    delete jwk.d; delete jwk.dp; delete jwk.dq; delete jwk.p; delete jwk.q; delete jwk.qi;
    jwk.key_ops = ["verify"];
    
    const publicKey = await window.crypto.subtle.importKey(
        "jwk", jwk, { name: "RSA-PSS", hash: "SHA-256" }, true, ["verify"]
    );

    const publicKeyBuffer = await window.crypto.subtle.exportKey("spki", publicKey);
    const publicKeyPem = formatPEM(arrayBufferToBase64(publicKeyBuffer), "PUBLIC KEY");
    const userId = await sha256Hex(publicKeyBuffer);

    return { publicKeyPem, privateKeyPem, userId, keyPair: { privateKey, publicKey } };
}

export async function signPayload(privateKey, payloadString) {
    const encoder = new TextEncoder();
    const data = encoder.encode(payloadString);
    
    // Using saltLength: 32 which matches SHA-256 digest length.
    // Python backend verifies with MAX_LENGTH which dynamically adapts to this salt.
    const signatureBuffer = await window.crypto.subtle.sign(
        { name: "RSA-PSS", saltLength: 32 },
        privateKey,
        data
    );
    return arrayBufferToBase64(signatureBuffer);
}

export async function solvePoW(challengeId, difficulty) {
    const prefix = "0".repeat(difficulty);
    let nonce = 0;
    const encoder = new TextEncoder();
    
    while (true) {
        const data = encoder.encode(challengeId + nonce.toString());
        const hash = await sha256Hex(data);
        if (hash.startsWith(prefix)) {
            return nonce.toString();
        }
        nonce++;
        if (nonce % 10000 === 0) {
            // Yield to main thread to prevent UI freezing
            await new Promise(resolve => setTimeout(resolve, 0));
        }
    }
}

let cachedFingerprint = null;
export async function getFingerprint() {
    if (cachedFingerprint) return cachedFingerprint;

    const components = [];
    
    // 1. Timezone & Locale
    components.push(Intl.DateTimeFormat().resolvedOptions().timeZone);
    components.push(navigator.language);
    
    // 2. Screen Resolution
    components.push(`${window.screen.width}x${window.screen.height}x${window.screen.colorDepth}`);
    
    // 3. Canvas Hash
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