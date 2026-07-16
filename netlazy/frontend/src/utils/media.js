export const audioBlobCache = new Map();

/**
 * Downloads reversed audio from CDN, decodes it, reverses it back to normal, 
 * and generates a valid WAV Blob URL for playback.
 */
export async function getRestoredAudioBlobUrl(url) {
    if (audioBlobCache.has(url)) return audioBlobCache.get(url);
    try {
        const res = await fetch(url);
        if (res.status === 404) return null; // File missing
        if (!res.ok) throw new Error("HTTP error");
        const arrayBuffer = await res.arrayBuffer();
        
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
        
        // Un-reverse the audio channels
        for (let i = 0; i < audioBuffer.numberOfChannels; i++) {
            Array.prototype.reverse.call(audioBuffer.getChannelData(i));
        }
        
        const wavBlob = audioBufferToWav(audioBuffer);
        const blobUrl = URL.createObjectURL(wavBlob);
        audioBlobCache.set(url, blobUrl);
        return blobUrl;
    } catch (e) {
        return null;
    }
}

// Lightweight AudioBuffer to WAV encoder
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