import axios from 'axios';
import { signPayload, getFingerprint, hashBody, solvePoW } from './crypto.js';
import { useStore } from '../store/state.js';
import { Capacitor } from '@capacitor/core';

const baseURL = Capacitor.isNativePlatform() 
    ? (import.meta.env.VITE_API_URL || 'https://nargan-projects.hf.space/netlazy/api')
    : '/netlazy/api';

const api = axios.create({
    baseURL: baseURL
});

function uuidv4() {
    return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, c =>
        (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    );
}

// Global request interceptor to inject cryptographic headers
api.interceptors.request.use(async (config) => {
    const store = useStore();

    let bodyBytes;
    if (config.data instanceof Blob) {
        bodyBytes = new Uint8Array(await config.data.arrayBuffer());
    } else if (config.data instanceof ArrayBuffer) {
        bodyBytes = new Uint8Array(config.data);
    } else if (config.data) {
        bodyBytes = JSON.stringify(config.data);
    } else {
        bodyBytes = new Uint8Array();
    }

    const bodyHash = await hashBody(bodyBytes);
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonce = uuidv4();
    const fingerprint = await getFingerprint();

    config.headers['X-Fingerprint'] = fingerprint;

    if (store.state.keyPair && store.state.userId) {
        const method = config.method.toUpperCase();

        const rawUrl = config.url || '';
        const qIndex = rawUrl.indexOf('?');
        const urlPath = qIndex === -1 ? rawUrl : rawUrl.slice(0, qIndex);
        let queryStr = qIndex === -1 ? '' : rawUrl.slice(qIndex + 1);

        if (config.params) {
            const paramsStr = new URLSearchParams(config.params).toString();
            queryStr = queryStr ? `${queryStr}&${paramsStr}` : paramsStr;
        }

        // Normalize URL to path only (removes scheme/domain to align signature checks with FastAPI)
        let path = `${config.baseURL || ''}${urlPath}`;
        if (path.includes('://')) {
            try {
                const parsedUrl = new URL(path);
                path = parsedUrl.pathname;
            } catch (e) {
                // Fallback to standard raw path
            }
        }

        const canonicalPayload = `${method}\n${path}\n${queryStr}\n${timestamp}\n${nonce}\n${bodyHash}`;
        const signatureBase64 = await signPayload(store.state.keyPair.privateKey, canonicalPayload);

        config.headers['X-User-Id'] = store.state.userId;
        config.headers['X-Timestamp'] = timestamp;
        config.headers['X-Nonce'] = nonce;
        config.headers['X-Signature'] = signatureBase64;
    }

    return config;
}, error => Promise.reject(error));


// Global response interceptor to handle auto-logout on cascade ban or key rotation
api.interceptors.response.use(response => response, error => {
    if (error.response && [401, 403].includes(error.response.status)) {
        const store = useStore();
        if (store.state.isRegistered) {
            if (error.response.status === 403) {
                store.state.isBanned = true;
            } else {
                store.logout();
                store.addToast("Session Expired", "bi-exclamation-triangle");
            }
        }
    }
    return Promise.reject(error);
});

export async function apiWithPoW(method, url, data) {
    const challengeRes = await api.get('/security/challenge');
    const { challenge_id, difficulty } = challengeRes.data;

    const powNonce = await solvePoW(challenge_id, difficulty);

    return api({
        method,
        url,
        data,
        headers: {
            'X-Challenge-Id': challenge_id,
            'X-Pow-Nonce': powNonce
        }
    });
}

export default api;