/**
 * Direct media pairs run in the browser on the official single-thread ffmpeg.wasm.
 * Anything else, including a missing core, returns null and the card uses the server.
 */
import { FFmpeg } from '../vendor/ffmpeg/loader/index.js'
import { toBlobURL } from '../vendor/ffmpeg/util/index.js'

const MEDIA = new Set(['mp4', 'webm', 'mp3', 'wav', 'ogg', 'gif'])
const TYPES = {
    mp4: 'video/mp4',
    webm: 'video/webm',
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
    ogg: 'audio/ogg',
    gif: 'image/gif',
}

let loading = null
let tail = Promise.resolve()
let ticket = 0

function engine() {
    if (!loading) {
        loading = (async () => {
            const core = new URL('../vendor/ffmpeg/core/ffmpeg-core.js', import.meta.url)
            const wasm = new URL('../vendor/ffmpeg/core/ffmpeg-core.wasm', import.meta.url)
            const ffmpeg = new FFmpeg()
            await ffmpeg.load({
                coreURL: await toBlobURL(core.href, 'text/javascript'),
                wasmURL: await toBlobURL(wasm.href, 'application/wasm'),
            })
            return ffmpeg
        })()
    }
    return loading
}

function exclusive(job) {
    const run = tail.then(job, job)
    tail = run.then(() => undefined, () => undefined)
    return run
}

window.Formular = window.Formular || {}

window.Formular.tryFfmpegWasm = (file, from, to) => exclusive(async () => {
    if (!MEDIA.has(from) || !MEDIA.has(to)) return null
    const id = ++ticket
    const input = `in-${id}.${from}`
    const output = `out-${id}.${to}`
    try {
        const ffmpeg = await engine()
        await ffmpeg.writeFile(input, new Uint8Array(await file.arrayBuffer()))
        const code = await ffmpeg.exec(['-i', input, output])
        if (code !== 0) return null
        const data = await ffmpeg.readFile(output)
        const bytes = data instanceof Uint8Array ? new Uint8Array(data) : null
        if (!bytes || bytes.byteLength === 0) return null
        return new Blob([bytes], { type: TYPES[to] || 'application/octet-stream' })
    } catch (error) {
        return null
    } finally {
        try {
            const ffmpeg = await loading
            if (ffmpeg) {
                await ffmpeg.deleteFile(input)
                await ffmpeg.deleteFile(output)
            }
        } catch (error) {}
    }
})
