(function () {
    function concat(chunks) {
        const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
        const out = new Uint8Array(total);
        let offset = 0;
        chunks.forEach((chunk) => {
            out.set(chunk, offset);
            offset += chunk.length;
        });
        return out;
    }

    function shrinkJpeg(bytes) {
        if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;
        const chunks = [bytes.subarray(0, 2)];
        let i = 2;
        let removed = 0;
        while (i < bytes.length) {
            if (bytes[i] !== 0xff) return null;
            while (i < bytes.length && bytes[i] === 0xff) i += 1;
            if (i >= bytes.length) return null;
            const marker = bytes[i];
            i += 1;
            if (marker === 0xd9) {
                chunks.push(Uint8Array.of(0xff, 0xd9));
                break;
            }
            if (marker === 0xda) {
                chunks.push(Uint8Array.of(0xff, 0xda));
                chunks.push(bytes.subarray(i));
                break;
            }
            if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
                chunks.push(Uint8Array.of(0xff, marker));
                continue;
            }
            if (i + 1 >= bytes.length) return null;
            const length = (bytes[i] << 8) | bytes[i + 1];
            if (length < 2 || i + length > bytes.length) return null;
            const segment = bytes.subarray(i - 2, i + length);
            if (marker === 0xe1 || marker === 0xfe) removed += segment.length;
            else chunks.push(segment);
            i += length;
        }
        if (!removed) return null;
        return concat(chunks);
    }

    function chunkName(bytes, offset) {
        return String.fromCharCode(
            bytes[offset],
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3]
        );
    }

    const PNG_DROP = new Set(['tEXt', 'zTXt', 'iTXt', 'eXIf', 'tIME']);

    function shrinkPng(bytes) {
        const signature = [137, 80, 78, 71, 13, 10, 26, 10];
        if (bytes.length < 8 || signature.some((value, index) => bytes[index] !== value)) return null;
        const chunks = [bytes.subarray(0, 8)];
        let i = 8;
        let removed = 0;
        while (i + 12 <= bytes.length) {
            const length = (bytes[i] * 16777216) + (bytes[i + 1] << 16) + (bytes[i + 2] << 8) + bytes[i + 3];
            if (i + 12 + length > bytes.length) return null;
            const name = chunkName(bytes, i + 4);
            const whole = bytes.subarray(i, i + 12 + length);
            if (PNG_DROP.has(name)) removed += whole.length;
            else chunks.push(whole);
            i += 12 + length;
            if (name === 'IEND') break;
        }
        if (!removed) return null;
        return concat(chunks);
    }

    async function shrinkZip(file) {
        if (!window.JSZip) return null;
        const zip = await window.JSZip.loadAsync(file);
        const packed = await zip.generateAsync({
            type: 'blob',
            compression: 'DEFLATE',
            compressionOptions: { level: 9 },
        });
        if (packed.size >= file.size) return null;
        return new File([packed], file.name, { type: file.type || 'application/zip' });
    }

    function asFile(bytes, file, type) {
        return new File([bytes], file.name, { type: type || file.type });
    }

    async function shrinkLossless(file) {
        if (file.size > 256 * 1024 * 1024) return null;
        const name = file.name.toLowerCase();
        const kind = (file.type || '').toLowerCase();
        if (name.endsWith('.zip') || kind === 'application/zip') {
            try {
                return await shrinkZip(file);
            } catch (error) {
                return null;
            }
        }
        const jpeg = name.endsWith('.jpg') || name.endsWith('.jpeg') || kind === 'image/jpeg';
        const png = name.endsWith('.png') || kind === 'image/png';
        if (!jpeg && !png) return null;
        const bytes = new Uint8Array(await file.arrayBuffer());
        const shrunk = jpeg ? shrinkJpeg(bytes) : shrinkPng(bytes);
        if (!shrunk || shrunk.length >= bytes.length) return null;
        return asFile(shrunk, file, jpeg ? 'image/jpeg' : 'image/png');
    }

    if (typeof window !== 'undefined') {
        window.Formular = window.Formular || {};
        window.Formular.shrinkLossless = shrinkLossless;
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { shrinkJpeg, shrinkPng };
    }
})();
