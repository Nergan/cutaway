export const mediaBlobCache = new Map();
const blobKeys = [];
const MAX_BLOBS = 60;

/**
 * Downloads polyglot media, attempts AES-256-GCM decryption if the magical payload separator is found.
 * Falls back to legacy parsing logic if missing.
 */
export async function fetchAndDecryptMedia(url, userId, mediaType) {
    if (mediaBlobCache.has(url)) return mediaBlobCache.get(url);
    try {
        const res = await fetch(url);
        if (res.status === 404) return null;
        if (!res.ok) throw new Error("HTTP error");
        const buffer = await res.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        
        const magic = new TextEncoder().encode("||NLZ_PAYLOAD||");
        let magicIndex = -1;
        
        for (let i = 0; i <= bytes.length - magic.length; i++) {
            if (bytes[i] === magic[0]) {
                let match = true;
                for (let j = 1; j < magic.length; j++) {
                    if (bytes[i + j] !== magic[j]) { match = false; break; }
                }
                if (match) { magicIndex = i; break; }
            }
        }

        let blobUrl;
        let isLegacy = false;

        if (magicIndex !== -1) {
            const payloadStart = magicIndex + magic.length;
            const iv = bytes.slice(payloadStart, payloadStart + 12);
            const ciphertext = bytes.slice(payloadStart + 12);
            
            const keyMaterial = await window.crypto.subtle.importKey(
                "raw", new TextEncoder().encode(userId),
                { name: "HKDF" }, false, ["deriveKey"]
            );
            const key = await window.crypto.subtle.deriveKey(
                { name: "HKDF", salt: new Uint8Array(32), info: new TextEncoder().encode("netlazy_media_key"), hash: "SHA-256" },
                keyMaterial,
                { name: "AES-GCM", length: 256 }, false, ["decrypt"]
            );
            
            const decryptedBuffer = await window.crypto.subtle.decrypt(
                { name: "AES-GCM", iv: iv }, key, ciphertext
            );
            
            const mime = mediaType === 'video' ? 'video/mp4' : (mediaType === 'audio' ? 'audio/mp3' : 'image/webp');
            const blob = new Blob([decryptedBuffer], { type: mime });
            blobUrl = URL.createObjectURL(blob);
        } else {
            isLegacy = true;
            if (mediaType === 'audio') {
                blobUrl = await getRestoredAudioBlobUrl(buffer);
            } else {
                blobUrl = url;
            }
        }

        const result = { blobUrl, isLegacy };
        mediaBlobCache.set(url, result);
        blobKeys.push(url);

        if (blobKeys.length > MAX_BLOBS) {
            const oldest = blobKeys.shift();
            const oldData = mediaBlobCache.get(oldest);
            if (oldData && oldData.blobUrl && oldData.blobUrl.startsWith('blob:')) {
                URL.revokeObjectURL(oldData.blobUrl);
            }
            mediaBlobCache.delete(oldest);
        }

        return result;
    } catch (e) {
        console.error("Decryption failed", e);
        return null;
    }
}

// Lightweight AudioBuffer to WAV encoder for legacy un-reversed audio
async function getRestoredAudioBlobUrl(arrayBuffer) {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    for (let i = 0; i < audioBuffer.numberOfChannels; i++) {
        Array.prototype.reverse.call(audioBuffer.getChannelData(i));
    }
    const wavBlob = audioBufferToWav(audioBuffer);
    return URL.createObjectURL(wavBlob);
}

function audioBufferToWav(buffer) {
    let numOfChan = buffer.numberOfChannels,
        length = buffer.length * numOfChan * 2 + 44,
        bufferArray = new ArrayBuffer(length),
        view = new DataView(bufferArray),
        channels = [], i, sample,
        offset = 0,
        pos = 0;

    setUint32(0x46464952);                         // "RIFF"
    setUint32(length - 8);                         // file length - 8
    setUint32(0x45564157);                         // "WAVE"
    setUint32(0x20746d66);                         // "fmt " chunk
    setUint32(16);                                 // length = 16
    setUint16(1);                                  // PCM (uncompressed)
    setUint16(numOfChan);
    setUint32(buffer.sampleRate);
    setUint32(buffer.sampleRate * 2 * numOfChan); // avg. bytes/sec
    setUint16(numOfChan * 2);                      // block-align
    setUint16(16);                                 // 16-bit

    setUint32(0x61746164);                         // "data" - chunk
    setUint32(length - pos - 4);                   // chunk length

    for(i = 0; i < buffer.numberOfChannels; i++) channels.push(buffer.getChannelData(i));

    while(pos < buffer.length) {
        for(i = 0; i < numOfChan; i++) {
            sample = Math.max(-1, Math.min(1, channels[i][pos])); 
            sample = (0.5 + sample < 0 ? sample * 32768 : sample * 32767)|0; 
            view.setInt16(offset, sample, true);          
            offset += 2;
        }
        pos++;
    }

    return new Blob([bufferArray], {type: "audio/wav"});

    function setUint16(data) { view.setUint16(offset, data, true); offset += 2; }
    function setUint32(data) { view.setUint32(offset, data, true); offset += 4; }
}