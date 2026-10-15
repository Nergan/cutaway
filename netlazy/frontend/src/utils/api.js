import axios from 'axios';
import { signHybridPayload, signIdentityPayload, signReaderPayload, getFingerprint, hashBody, solvePoW } from './crypto.js';
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

let chainTail = Promise.resolve();

function acquireChain() {
    let release;
    const released = new Promise((resolve) => { release = resolve; });
    const waitFor = chainTail;
    chainTail = waitFor.then(() => released);
    return waitFor.then(() => release);
}

function releaseChain(config) {
    if (config && typeof config.__releaseChain === 'function') {
        const release = config.__releaseChain;
        config.__releaseChain = null;
        release();
    }
}

function isPublicPath(path) {
    return path.includes('/tags') || path.endsWith('/security/challenge');
}

function isReaderRequest(method, path) {
    if (method === 'GET') return !path.endsWith('/auth/anchor');
    return method === 'POST' && path.endsWith('/feed/search');
}

async function requestBodyBytes(data) {
    if (data == null) return new Uint8Array();
    if (typeof data === 'string') return data;
    if (data instanceof Blob) return new Uint8Array(await data.arrayBuffer());
    if (data instanceof ArrayBuffer) return new Uint8Array(data);
    if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    return JSON.stringify(data);
}

api.interceptors.request.use(async (config) => {
    const store = useStore();

    const bodyBytes = await requestBodyBytes(config.data);
    const bodyHash = await hashBody(bodyBytes);
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonce = uuidv4();
    const fingerprint = await getFingerprint();

    config.headers['X-Fingerprint'] = fingerprint;

    const rawUrl = config.url || '';
    const qIndex = rawUrl.indexOf('?');
    const urlPath = qIndex === -1 ? rawUrl : rawUrl.slice(0, qIndex);
    let queryStr = qIndex === -1 ? '' : rawUrl.slice(qIndex + 1);

    if (config.params) {
        const paramsStr = new URLSearchParams(config.params).toString();
        queryStr = queryStr ? `${queryStr}&${paramsStr}` : paramsStr;
    }

    let path = `${config.baseURL || ''}${urlPath}`;
    if (path.includes('://')) {
        try {
            const parsedUrl = new URL(path);
            path = parsedUrl.pathname;
        } catch (e) {}
    }

    const method = (config.method || 'get').toUpperCase();
    const isAnchorEndpoint = path.endsWith('/auth/anchor');
    const isRegisterEndpoint = path.endsWith('/auth/register');
    const publicRequest = isPublicPath(path);
    const readerRequest = !publicRequest && isReaderRequest(method, path);

    config.__reader = readerRequest;
    config.headers['X-Signed-Path'] = path;

    const shouldSign = !publicRequest && (store.state.isRegistered || isAnchorEndpoint) && store.state.userId && !isRegisterEndpoint;

    if (!shouldSign) {
        return config;
    }

    delete config.headers['X-Chain-Anchor'];
    delete config.headers['X-Timestamp'];
    delete config.headers['X-Nonce'];
    delete config.headers['X-Body-Hash'];
    delete config.headers['X-Signature-Ed25519'];
    delete config.headers['X-Signature-MLDSA'];

    let release = null;
    if (!isAnchorEndpoint && !readerRequest) {
        release = await acquireChain();
    }

    try {
        let edSig, pqSig;
        if (isAnchorEndpoint) {
            const sigs = await signIdentityPayload(method, path, timestamp, nonce, bodyHash);
            edSig = sigs.edSig;
            pqSig = sigs.pqSig;
        } else if (readerRequest) {
            const sigs = await signReaderPayload(method, path, queryStr, timestamp, nonce, bodyHash);
            edSig = sigs.edSig;
            pqSig = sigs.pqSig;
        } else {
            const prevAnchor = store.state.currentAnchor || '';
            const canonicalPayload = `PQDA-v1\n${method}\n${path}\n${queryStr}\n${timestamp}\n${nonce}\n${bodyHash}\n${prevAnchor}`;
            const sigs = await signHybridPayload(canonicalPayload);
            edSig = sigs.edSig;
            pqSig = sigs.pqSig;
            config.headers['X-Chain-Anchor'] = prevAnchor;
            config.__releaseChain = release;
            release = null;
        }

        config.headers['X-User-Id'] = store.state.userId;
        config.headers['X-Timestamp'] = timestamp;
        config.headers['X-Nonce'] = nonce;
        config.headers['X-Body-Hash'] = bodyHash;
        config.headers['X-Signature-Ed25519'] = edSig;
        config.headers['X-Signature-MLDSA'] = pqSig;
        return config;
    } catch (error) {
        if (release) release();
        throw error;
    }
}, error => Promise.reject(error));


let isResyncing = false;
let resyncQueue = [];

api.interceptors.response.use(response => {
    const store = useStore();
    if (response.config && response.config.__releaseChain && response.headers['x-next-anchor']) {
        store.state.currentAnchor = response.headers['x-next-anchor'];
    }
    releaseChain(response.config);
    if (store && store.state.authErrorNotified) {
        store.state.authErrorNotified = false;
    }
    return response;
}, async error => {
    const store = useStore();
    try {
        if (!error.response || ![401, 403, 409].includes(error.response.status)) {
            return Promise.reject(error);
        }

        if (error.response.status === 403) {
            store.state.isBanned = true;
            return Promise.reject(error);
        }

        const detail = error.response.data?.detail || '';
        if (detail === "Unknown user") {
            await store.logout();
            return Promise.reject(error);
        }

        const originalRequest = error.config;
        if (!originalRequest || originalRequest.__reader || !store.state.isRegistered) {
            return Promise.reject(error);
        }

        const isAnchorUrl = originalRequest.url && originalRequest.url.endsWith('/auth/anchor');
        if (originalRequest._retry || isAnchorUrl) {
            return Promise.reject(error);
        }

        originalRequest._retry = true;

        if (isResyncing) {
            return new Promise((resolve, reject) => {
                resyncQueue.push({ resolve: () => resolve(api(originalRequest)), reject });
            });
        }

        isResyncing = true;
        try {
            const anchorRes = await api.get('/auth/anchor');
            store.state.currentAnchor = anchorRes.data.current_anchor;
            isResyncing = false;

            const queue = resyncQueue;
            resyncQueue = [];
            queue.forEach(cb => cb.resolve());

            return api(originalRequest);
        } catch (err) {
            isResyncing = false;
            const queue = resyncQueue;
            resyncQueue = [];
            const errDetail = err.response?.data?.detail;
            if (errDetail === "Unknown user") {
                await store.logout();
                store.addToast("Account not found. Logged out.", "bi-box-arrow-right");
            } else if (!store.state.authErrorNotified) {
                store.addToast("Chain desynced. Please reload.", "bi-exclamation-triangle");
                store.state.authErrorNotified = true;
            }
            queue.forEach(cb => cb.reject(err));
            return Promise.reject(err);
        }
    } finally {
        releaseChain(error.config);
    }
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