import api from './api.js';

export const blobCache = new Map();

export async function getDecryptedMedia(url, mediaType) {
    if (blobCache.has(url)) return blobCache.get(url);
    
    try {
        const response = await fetch(url);
        if (response.status === 404) return null; // File missing
        if (!response.ok) throw new Error("HTTP " + response.status);
        
        const buffer = await response.arrayBuffer();
        const view = new Uint8Array(buffer);
        
        // Reverse deterministic distortion (XOR cipher)
        for (let i = 0; i < view.length; i++) {
            view[i] ^= 0x42;
        }
        
        let mime = 'application/octet-stream';
        if (mediaType === 'image') mime = 'image/webp';
        if (mediaType === 'video') mime = 'video/mp4';
        if (mediaType === 'audio') mime = 'audio/mp3';
        
        const blob = new Blob([view], { type: mime });
        const blobUrl = URL.createObjectURL(blob);
        blobCache.set(url, blobUrl);
        return blobUrl;
    } catch (e) {
        throw e;
    }
}

export async function processMediaBlobs(mediaList, isMyProfile = false) {
    if (!mediaList) return;
    for (const m of mediaList) {
        if (!m.blobUrl && m.url && !m.isUploading) {
            getDecryptedMedia(m.url, m.media_type).then(blobUrl => {
                if (blobUrl === null) {
                    m.isMissing = true; // Mark as dead
                    if (isMyProfile) {
                        // Automatically silently clean up dead CDN links from our local DB
                        api.delete(`/profile/me/media?url=${encodeURIComponent(m.url)}`).catch(()=>{});
                    }
                } else if (blobUrl) {
                    m.blobUrl = blobUrl;
                    m.isLoaded = true;
                }
            }).catch(e => {
                m.isError = true;
            });
        }
    }
}