/* Sky palette. Place and date come from the browser, then the light
   outside comes from sunrise-sunset.org and Open-Meteo's shortwave
   radiation, so a summer 05:00 is already morning. Clouds and rain
   cool that light, and each part of the world lends its own tint. */

const HOUR = 60 * 60 * 1000;
const CACHE_KEY = 'netlazy-daylight-sky-v2';
const PAUSE_KEY = 'netlazy-daylight-paused';

export const COLOR_KEYS = [
    '--bg-base', '--bg-surface', '--bg-elevated',
    '--border-subtle', '--border-focus',
    '--text-main', '--text-muted',
    '--accent-moss', '--accent-danger', '--accent-info', '--accent-earth',
];

const SKY = {
    night: {
        '--bg-base': '#05060a',
        '--bg-surface': '#0c1018',
        '--bg-elevated': '#151b28',
        '--border-subtle': '#2c3548',
        '--border-focus': '#7d8ba3',
        '--text-main': '#f4f1ea',
        '--text-muted': '#a9b2c2',
        '--accent-moss': '#9aaf86',
        '--accent-danger': '#d08b80',
        '--accent-info': '#8eb0c2',
        '--accent-earth': '#d2c2a2',
    },
    blue: {
        '--bg-base': '#1a2744',
        '--bg-surface': '#223052',
        '--bg-elevated': '#2b3b64',
        '--border-subtle': '#46557a',
        '--border-focus': '#8ea0c4',
        '--text-main': '#f6f2ea',
        '--text-muted': '#c5cce0',
        '--accent-moss': '#a3b896',
        '--accent-danger': '#e0a097',
        '--accent-info': '#a9c6d4',
        '--accent-earth': '#e0d0b0',
    },
    dawn: {
        '--bg-base': '#f7d8c8',
        '--bg-surface': '#f8e3d6',
        '--bg-elevated': '#fbeee6',
        '--border-subtle': '#e7c3b4',
        '--border-focus': '#c98b9a',
        '--text-main': '#4a2e32',
        '--text-muted': '#8d5d66',
        '--accent-moss': '#6f8a52',
        '--accent-danger': '#b85a52',
        '--accent-info': '#5d7f90',
        '--accent-earth': '#a07d4e',
    },
    morning: {
        '--bg-base': '#fff4ea',
        '--bg-surface': '#fff8f3',
        '--bg-elevated': '#fffdfb',
        '--border-subtle': '#f0e0d2',
        '--border-focus': '#d7b89a',
        '--text-main': '#3a312c',
        '--text-muted': '#7d6d64',
        '--accent-moss': '#6e8a4e',
        '--accent-danger': '#b85a52',
        '--accent-info': '#5d7f90',
        '--accent-earth': '#9c7d4a',
    },
    day: {
        '--bg-base': '#ffffff',
        '--bg-surface': '#f7f7f7',
        '--bg-elevated': '#f2f2f2',
        '--border-subtle': '#e6e6e6',
        '--border-focus': '#bdbdbd',
        '--text-main': '#232323',
        '--text-muted': '#666666',
        '--accent-moss': '#68854c',
        '--accent-danger': '#a3483b',
        '--accent-info': '#4a7787',
        '--accent-earth': '#9c855a',
    },
    golden: {
        '--bg-base': '#f8d7ae',
        '--bg-surface': '#fbe4c4',
        '--bg-elevated': '#fdecd6',
        '--border-subtle': '#e8c89a',
        '--border-focus': '#d09a58',
        '--text-main': '#3d2c18',
        '--text-muted': '#8a6844',
        '--accent-moss': '#6d8848',
        '--accent-danger': '#b85a48',
        '--accent-info': '#5e7e90',
        '--accent-earth': '#9a7040',
    },
    sunset: {
        '--bg-base': '#f6c09a',
        '--bg-surface': '#f8cbaa',
        '--bg-elevated': '#fad8be',
        '--border-subtle': '#e2a67e',
        '--border-focus': '#c47a48',
        '--text-main': '#3a2014',
        '--text-muted': '#8a5340',
        '--accent-moss': '#6a8448',
        '--accent-danger': '#9a4038',
        '--accent-info': '#5a7088',
        '--accent-earth': '#8a6238',
    },
    dusk: {
        '--bg-base': '#243056',
        '--bg-surface': '#2c3a64',
        '--bg-elevated': '#364674',
        '--border-subtle': '#4d5d88',
        '--border-focus': '#8ea0c8',
        '--text-main': '#f3efe6',
        '--text-muted': '#c0c6da',
        '--accent-moss': '#a8bc96',
        '--accent-danger': '#e0a8a0',
        '--accent-info': '#b0d0dc',
        '--accent-earth': '#e4d4b4',
    },
};

function smooth(t) {
    const x = Math.min(1, Math.max(0, t));
    return x * x * (3 - 2 * x);
}

function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mixHex(a, b, t) {
    const from = hexToRgb(a);
    const to = hexToRgb(b);
    const channels = from.map((channel, i) => {
        const left = Math.pow(channel / 255, 2.2);
        const right = Math.pow(to[i] / 255, 2.2);
        const mixed = Math.pow(left + (right - left) * t, 1 / 2.2);
        return Math.max(0, Math.min(255, Math.round(mixed * 255)));
    });
    return `#${channels.map(channel => channel.toString(16).padStart(2, '0')).join('')}`;
}

function mixPalettes(a, b, t) {
    if (t <= 0) return a;
    if (t >= 1) return b;
    const mixed = {};
    for (const key of COLOR_KEYS) mixed[key] = mixHex(a[key], b[key], t);
    return mixed;
}

function relLuminance(hex) {
    const linear = hexToRgb(hex).map(channel => {
        const s = channel / 255;
        return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function parseTime(value) {
    if (!value || typeof value !== 'string') return null;
    const ms = Date.parse(value);
    if (!Number.isFinite(ms) || ms < Date.parse('2000-01-01T00:00:00Z')) return null;
    return ms;
}

export function localStampToUtc(stamp, offsetSeconds) {
    if (typeof stamp !== 'string') return NaN;
    if (/[zZ]|[+-]\d\d:\d\d$/.test(stamp)) return Date.parse(stamp);
    const utc = Date.parse(stamp.length === 16 ? `${stamp}:00Z` : `${stamp}Z`);
    return utc - (Number(offsetSeconds) || 0) * 1000;
}

export function skyFrames(sun) {
    if (!sun) return [];
    const rise = sun.sunrise;
    const set = sun.sunset;
    const noon = sun.solarNoon;
    const points = [];
    const add = (name, at) => {
        if (Number.isFinite(at)) points.push({ name, at });
    };

    add('night', sun.nauticalBegin);
    add('blue', sun.civilBegin);
    add('dawn', rise);
    if (Number.isFinite(rise)) add('morning', rise + 0.55 * HOUR);

    const sunUp = Number.isFinite(rise) && Number.isFinite(set);
    const midnightSun = Number.isFinite(noon) && !Number.isFinite(rise) && !Number.isFinite(set)
        && !Number.isFinite(sun.civilBegin) && !Number.isFinite(sun.nauticalBegin);
    if (midnightSun) {
        add('day', noon - 12 * HOUR);
        add('day', noon + 12 * HOUR);
    } else if (sunUp && Number.isFinite(noon)) {
        const dayStart = Math.max(noon - 1.6 * HOUR, rise + 0.9 * HOUR);
        const dayEnd = Math.min(noon + 1.6 * HOUR, set - 0.9 * HOUR);
        if (dayEnd - dayStart >= 20 * 60 * 1000) {
            add('day', dayStart);
            add('day', dayEnd);
        }
    }
    if (Number.isFinite(set)) {
        const goldenAt = set - 0.7 * HOUR;
        if (!Number.isFinite(rise) || goldenAt > rise + 0.6 * HOUR) add('golden', goldenAt);
    }
    add('sunset', set);
    add('dusk', sun.civilEnd);
    add('night', sun.nauticalEnd);

    points.sort((a, b) => a.at - b.at);
    const ordered = [];
    for (const point of points) {
        if ((point.name === 'day' || point.name === 'morning' || point.name === 'golden') && Number.isFinite(rise) && point.at < rise) continue;
        if ((point.name === 'day' || point.name === 'morning' || point.name === 'golden') && Number.isFinite(set) && point.at > set) continue;
        const at = ordered.length && point.at <= ordered[ordered.length - 1].at
            ? ordered[ordered.length - 1].at + 60 * 1000
            : point.at;
        ordered.push({ name: point.name, at });
    }
    return ordered;
}

function sampleFrames(now, frames) {
    if (!frames.length) return null;
    if (now <= frames[0].at) return SKY[frames[0].name];
    const last = frames[frames.length - 1];
    if (now >= last.at) return SKY[last.name];
    for (let i = 0; i < frames.length - 1; i++) {
        const a = frames[i];
        const b = frames[i + 1];
        if (now >= a.at && now <= b.at) {
            const t = smooth((now - a.at) / (b.at - a.at || 1));
            return mixPalettes(SKY[a.name], SKY[b.name], t);
        }
    }
    return SKY[last.name];
}

function spanAt(samples, now) {
    if (!samples || !samples.length) return null;
    if (now <= samples[0].at) return { a: samples[0], b: samples[0], t: 0 };
    const last = samples[samples.length - 1];
    if (now >= last.at) return { a: last, b: last, t: 0 };
    for (let i = 0; i < samples.length - 1; i++) {
        const a = samples[i];
        const b = samples[i + 1];
        if (now >= a.at && now <= b.at) {
            return { a, b, t: (now - a.at) / (b.at - a.at || 1) };
        }
    }
    return { a: last, b: last, t: 0 };
}

function valueAt(samples, now) {
    const span = spanAt(samples, now);
    if (!span) return null;
    return span.a.watts + (span.b.watts - span.a.watts) * span.t;
}

function lightLevel(samples, now) {
    const watts = valueAt(samples, now);
    if (watts == null) return null;
    const peak = samples.reduce((max, sample) => Math.max(max, Number(sample.watts) || 0), 0);
    if (peak < 8) return 0;
    return Math.max(0, Math.min(1, watts / peak));
}

function isRising(samples, now) {
    const nowWatts = valueAt(samples, now);
    const thenWatts = valueAt(samples, now - 45 * 60 * 1000);
    if (nowWatts == null || thenWatts == null) return true;
    return nowWatts >= thenWatts - 1;
}

function paletteFromLight(light, rising) {
    const stops = rising
        ? [[0, 'night'], [0.04, 'blue'], [0.12, 'dawn'], [0.28, 'morning'], [0.62, 'day']]
        : [[0, 'night'], [0.04, 'dusk'], [0.14, 'sunset'], [0.32, 'golden'], [0.62, 'day']];
    const x = Math.max(0, Math.min(1, light));
    if (x <= stops[0][0]) return SKY[stops[0][1]];
    for (let i = 0; i < stops.length - 1; i++) {
        const [a, aName] = stops[i];
        const [b, bName] = stops[i + 1];
        if (x >= a && x <= b) return mixPalettes(SKY[aName], SKY[bName], smooth((x - a) / (b - a || 1)));
    }
    return SKY.day;
}

// south, north, west, east, tint, amount. Earlier rows win.
const PLACES = [
    ['sahara', 16, 31, -17, 36, '#e4c48a', 0.2],
    ['arabian', 12, 32, 35, 60, '#e2bc90', 0.18],
    ['sonoran', 31, 36.5, -116, -108, '#e0b888', 0.18],
    ['gobi', 38, 48, 90, 120, '#d2b48c', 0.16],
    ['outback', -32, -19, 121, 145, '#e0b07a', 0.2],
    ['kalahari', -28, -20, 17, 26, '#d7b48a', 0.16],
    ['atacama', -30, -18, -72, -67, '#d9c4a0', 0.16],
    ['amazon', -14, 5, -78, -48, '#6f9a5c', 0.2],
    ['congo', -8, 6, 8, 32, '#678f58', 0.2],
    ['indonesia', -11, 8, 95, 141, '#5f9460', 0.18],
    ['taiga', 55, 70, 50, 165, '#6d8f62', 0.16],
    ['boreal', 50, 64, -141, -70, '#6a8c66', 0.14],
    ['scandinavia', 58, 71, 4, 32, '#6e9474', 0.14],
    ['alps', 44, 48.2, 5.5, 16.5, '#9aa8b4', 0.14],
    ['himalaya', 26, 36, 72, 98, '#8ea0b0', 0.16],
    ['west-coast', 32, 49, -125, -117, '#7eadc4', 0.16],
    ['east-coast', 25, 45, -82, -68, '#7eabc2', 0.14],
    ['great-lakes', 41, 49, -93, -76, '#86b0c4', 0.14],
    ['rockies', 35, 55, -116, -104, '#97a6b2', 0.12],
    ['andes', -46, 10, -78, -66, '#8e9eae', 0.14],
    ['mediterranean', 30, 45, -6, 37, '#c6b48a', 0.12],
    ['japan', 30, 46, 129, 146, '#7eaaa8', 0.14],
    ['british-isles', 49, 61, -11, 2, '#8eb4c6', 0.16],
    ['caribbean', 9, 27, -90, -59, '#6eb8c0', 0.16],
    ['hawaii', 18, 23, -161, -154, '#6ec4c2', 0.18],
    ['new-zealand', -48, -34, 166, 179, '#7eae9a', 0.14],
    ['plains', 31, 49, -104, -95, '#c6be8a', 0.12],
    ['steppe', 44, 55, 46, 86, '#c8bc84', 0.12],
    ['greenland', 60, 84, -74, -12, '#c9d8e6', 0.16],
    ['arctic', 70, 90, -180, 180, '#c5d6e4', 0.16],
    ['antarctica', -90, -60, -180, 180, '#d5e4f0', 0.18],
    ['europe', 35, 72, -12, 40, '#d2c8b0', 0.1],
    ['north-africa', 8, 37, -18, 40, '#dcc49a', 0.14],
    ['central-africa', -12, 8, -18, 42, '#6e945c', 0.16],
    ['southern-africa', -35, -12, 10, 42, '#c2b484', 0.12],
    ['middle-east', 12, 42, 32, 64, '#e0c49a', 0.16],
    ['south-asia', 5, 36, 60, 95, '#d2c09a', 0.12],
    ['east-asia', 20, 54, 100, 146, '#b7c6a6', 0.1],
    ['southeast-asia', -10, 23, 92, 152, '#6f9864', 0.16],
    ['north-asia', 45, 75, 40, 180, '#8aa484', 0.12],
    ['north-america', 24, 72, -168, -52, '#a8b89a', 0.1],
    ['central-america', 7, 24, -110, -77, '#6e9860', 0.16],
    ['south-america', -56, 13, -82, -34, '#7ea06a', 0.14],
    ['australia', -44, -10, 112, 154, '#c6b48a', 0.12],
];

const WEATHER = {
    cloud: { light: '#c3ced8', dark: '#141c28', amount: 0.32 },
    rain: { light: '#6a84a0', dark: '#152844', amount: 0.58 },
    storm: { light: '#4e6884', dark: '#101a2c', amount: 0.7 },
    snow: { light: '#d5e2f0', dark: '#1c2838', amount: 0.4 },
    fog: { light: '#c5ced6', dark: '#1a222c', amount: 0.46 },
};

function inBox(lat, lon, south, north, west, east) {
    if (lat < south || lat > north) return false;
    if (west <= east) return lon >= west && lon <= east;
    return lon >= west || lon <= east;
}

export function regionFor(lat, lon) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    for (const place of PLACES) {
        if (inBox(lat, lon, place[1], place[2], place[3], place[4])) {
            return { id: place[0], tint: place[5], amount: place[6] };
        }
    }
    return { id: 'ocean', tint: '#8eb6c8', amount: 0.14 };
}

function tintSurfaces(colors, hex, amount) {
    if (!hex || amount <= 0) return colors;
    const tinted = { ...colors };
    for (const key of ['--bg-base', '--bg-surface', '--bg-elevated', '--border-subtle']) {
        tinted[key] = mixHex(colors[key], hex, amount);
    }
    tinted['--accent-earth'] = mixHex(colors['--accent-earth'], hex, Math.min(0.45, amount));
    return tinted;
}

function applyRegion(colors, lat, lon) {
    const region = regionFor(lat, lon);
    if (!region) return colors;
    return tintSurfaces(colors, region.tint, region.amount);
}

function sampleWeather(samples, now) {
    if (!samples || !samples.some(sample => Number.isFinite(sample.cloud) || Number.isFinite(sample.code))) return null;
    const span = spanAt(samples, now);
    if (!span) return null;
    const num = (value, fallback) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    };
    return {
        cloud: num(span.a.cloud, 0) + (num(span.b.cloud, 0) - num(span.a.cloud, 0)) * span.t,
        rain: num(span.a.rain, 0) + (num(span.b.rain, 0) - num(span.a.rain, 0)) * span.t,
        code: span.t < 0.5 ? span.a.code : span.b.code,
    };
}

function weatherSpec(weather) {
    const code = Math.round(Number(weather.code) || 0);
    const cloud = Math.max(0, Math.min(100, Number(weather.cloud) || 0));
    const rain = Math.max(0, Number(weather.rain) || 0);
    if (code >= 95) return WEATHER.storm;
    if ((code >= 71 && code <= 77) || code === 85 || code === 86) return WEATHER.snow;
    if (code === 45 || code === 48) return WEATHER.fog;
    if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82) || rain >= 0.2) {
        if (code >= 65 || code === 67 || code === 82 || rain >= 4) return WEATHER.storm;
        return WEATHER.rain;
    }
    if (code === 3 || cloud >= 85) return WEATHER.cloud;
    if (code === 2 || cloud >= 55) {
        return { ...WEATHER.cloud, amount: WEATHER.cloud.amount * (0.45 + cloud / 220) };
    }
    return null;
}

function applyWeather(colors, weather) {
    const spec = weather && weatherSpec(weather);
    if (!spec) return colors;
    const dark = relLuminance(colors['--bg-base']) < 0.35;
    const amount = dark ? spec.amount * 0.55 : spec.amount;
    return tintSurfaces(colors, dark ? spec.dark : spec.light, amount);
}

function settleText(colors) {
    const bg = relLuminance(colors['--bg-base']);
    const text = relLuminance(colors['--text-main']);
    if (text < 0.45 && bg < 0.2) {
        return { ...colors, '--text-main': '#f3efe6', '--text-muted': '#c5ced8' };
    }
    if (text >= 0.45 && bg > 0.72) {
        return { ...colors, '--text-main': '#232323', '--text-muted': '#5c6570' };
    }
    return colors;
}

export function paletteAt(now, sun, samples = [], place = null) {
    const light = lightLevel(samples, now);
    const rising = isRising(samples, now);
    const frames = skyFrames(sun);
    let colors = frames.length ? sampleFrames(now, frames) : (light == null ? null : paletteFromLight(light, rising));
    if (!colors) return null;
    if (light != null && relLuminance(colors['--bg-base']) < 0.34 && light > 0.22) {
        const t = Math.min(1, (light - 0.22) / 0.5);
        colors = mixPalettes(colors, paletteFromLight(light, rising), t);
    }
    if (place) colors = applyRegion(colors, Number(place.lat), Number(place.lon));
    colors = applyWeather(colors, sampleWeather(samples, now));
    return settleText(colors);
}

function browserTz() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch (e) {
        return 'UTC';
    }
}

export function localDate(timeZone, now = new Date()) {
    try {
        return new Intl.DateTimeFormat('en-CA', {
            timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
        }).format(now);
    } catch (e) {
        return new Intl.DateTimeFormat('en-CA', {
            year: 'numeric', month: '2-digit', day: '2-digit',
        }).format(now);
    }
}

function withTimeout(ms) {
    if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') return AbortSignal.timeout(ms);
    const controller = new AbortController();
    setTimeout(() => controller.abort(), ms);
    return controller.signal;
}

async function fetchJson(url) {
    const response = await fetch(url, { signal: withTimeout(8000) });
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
}

function readCache() {
    try {
        const raw = sessionStorage.getItem(CACHE_KEY);
        if (!raw) return null;
        const data = JSON.parse(raw);
        if (!data || !Number.isFinite(data.lat) || !Number.isFinite(data.lon)) return null;
        return data;
    } catch (e) {
        return null;
    }
}

function writeCache(sky) {
    try {
        sessionStorage.setItem(CACHE_KEY, JSON.stringify(sky));
    } catch (e) {}
}

async function locate(fallbackTz) {
    const tz = fallbackTz || browserTz();
    try {
        const data = await fetchJson('https://get.geojs.io/v1/ip/geo.json');
        const lat = Number(data.latitude);
        const lon = Number(data.longitude);
        if (Number.isFinite(lat) && Number.isFinite(lon)) {
            const zone = data.timezone || tz;
            return { lat, lon, tz: zone, date: localDate(zone) };
        }
    } catch (e) {}
    try {
        const data = await fetchJson('https://ipwho.is/');
        const lat = Number(data && data.latitude);
        const lon = Number(data && data.longitude);
        const zone = data && (typeof data.timezone === 'string' ? data.timezone : data.timezone && data.timezone.id) || tz;
        if (data && data.success !== false && Number.isFinite(lat) && Number.isFinite(lon)) {
            return { lat, lon, tz: zone, date: localDate(zone) };
        }
    } catch (e) {}
    const city = String(tz.split('/').pop() || '').replace(/_/g, ' ');
    if (city && city !== 'UTC') {
        try {
            const data = await fetchJson(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1`);
            const hit = data.results && data.results[0];
            if (hit && Number.isFinite(hit.latitude) && Number.isFinite(hit.longitude)) {
                const zone = hit.timezone || tz;
                return { lat: hit.latitude, lon: hit.longitude, tz: zone, date: localDate(zone) };
            }
        } catch (e) {}
    }
    const offsetMin = -new Date().getTimezoneOffset();
    return {
        lat: 48,
        lon: Math.max(-180, Math.min(180, (offsetMin / 60) * 15)),
        tz,
        date: localDate(tz),
    };
}

async function fetchSun(place) {
    const url = `https://api.sunrise-sunset.org/json?lat=${place.lat}&lng=${place.lon}&formatted=0&date=${place.date}`;
    const data = await fetchJson(url);
    if (!data || data.status !== 'OK' || !data.results) return null;
    const row = data.results;
    const sun = {
        nauticalBegin: parseTime(row.nautical_twilight_begin),
        civilBegin: parseTime(row.civil_twilight_begin),
        sunrise: parseTime(row.sunrise),
        solarNoon: parseTime(row.solar_noon),
        sunset: parseTime(row.sunset),
        civilEnd: parseTime(row.civil_twilight_end),
        nauticalEnd: parseTime(row.nautical_twilight_end),
    };
    if (!Object.values(sun).some(Number.isFinite)) return null;
    return sun;
}

function readForecast(payload) {
    const hourly = payload && payload.hourly;
    const times = hourly && hourly.time;
    const watts = hourly && hourly.shortwave_radiation;
    if (!Array.isArray(times) || !Array.isArray(watts)) return [];
    const clouds = hourly.cloud_cover || [];
    const rain = hourly.precipitation || [];
    const codes = hourly.weather_code || [];
    const offset = Number(payload.utc_offset_seconds) || 0;
    const samples = [];
    for (let i = 0; i < times.length; i++) {
        const value = Number(watts[i]);
        const at = localStampToUtc(times[i], offset);
        if (!Number.isFinite(at) || !Number.isFinite(value)) continue;
        const cloud = Number(clouds[i]);
        const wet = Number(rain[i]);
        const code = Number(codes[i]);
        samples.push({
            at,
            watts: Math.max(0, value),
            cloud: Number.isFinite(cloud) ? cloud : 0,
            rain: Number.isFinite(wet) ? Math.max(0, wet) : 0,
            code: Number.isFinite(code) ? code : 0,
        });
    }
    samples.sort((a, b) => a.at - b.at);
    return samples;
}

async function fetchForecast(place) {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${place.lat}&longitude=${place.lon}&hourly=shortwave_radiation,cloud_cover,precipitation,weather_code&timezone=auto&forecast_days=2&past_days=1`;
    return readForecast(await fetchJson(url));
}

async function loadSky() {
    const cached = readCache();
    const tzGuess = (cached && cached.tz) || browserTz();
    const today = localDate(tzGuess);
    const fresh = cached && cached.date === today && Date.now() - cached.fetchedAt < 3 * HOUR;
    if (fresh && (cached.sun || (cached.samples && cached.samples.length))) return cached;

    const place = await locate(tzGuess);
    const [sun, samples] = await Promise.all([
        fetchSun(place).catch(() => null),
        fetchForecast(place).catch(() => []),
    ]);
    if (!sun && (!samples || !samples.length)) return cached;
    const sky = {
        lat: place.lat,
        lon: place.lon,
        tz: place.tz,
        date: place.date,
        fetchedAt: Date.now(),
        sun,
        samples: samples || [],
    };
    writeCache(sky);
    return sky;
}

let timer = 0;
let settleTimer = 0;
let paused = false;
let painted = false;
let misses = 0;
let onLight = null;

function paint(colors) {
    const body = document.body;
    if (!body || paused) return;
    const light = relLuminance(colors['--text-main']) < 0.45;
    const first = !painted;
    painted = true;
    misses = 0;
    body.classList.add('daylight');
    const write = () => {
        if (paused) return;
        for (const key of COLOR_KEYS) body.style.setProperty(key, colors[key]);
        body.classList.toggle('light-theme', light);
        if (onLight) onLight(light);
        if (first) {
            settleTimer = window.setTimeout(() => {
                if (!paused) body.classList.add('daylight-live');
            }, 1500);
        }
    };
    if (first) requestAnimationFrame(() => requestAnimationFrame(write));
    else write();
}

function stopQuietly() {
    if (timer) window.clearInterval(timer);
    timer = 0;
    document.removeEventListener('visibilitychange', onVisible);
}

async function tick() {
    if (paused || typeof document === 'undefined') return;
    try {
        const sky = await loadSky();
        if (paused) return;
        const colors = sky ? paletteAt(Date.now(), sky.sun, sky.samples || [], sky) : null;
        if (!colors) {
            misses += 1;
            if (misses >= 3 && !painted) stopQuietly();
            return;
        }
        paint(colors);
    } catch (e) {
        misses += 1;
        if (misses >= 3 && !painted) stopQuietly();
    }
}

function onVisible() {
    if (!document.hidden && !paused) tick();
}

export function daylightRunning() {
    return Boolean(timer) && !paused;
}

export function pauseDaylight() {
    paused = true;
    try { sessionStorage.setItem(PAUSE_KEY, '1'); } catch (e) {}
    stopQuietly();
    if (settleTimer) window.clearTimeout(settleTimer);
    settleTimer = 0;
    painted = false;
    if (typeof document === 'undefined') return;
    const body = document.body;
    body.classList.remove('daylight', 'daylight-live');
    for (const key of COLOR_KEYS) body.style.removeProperty(key);
}

export function startDaylight(options = {}) {
    if (typeof document === 'undefined') return;
    try {
        if (sessionStorage.getItem(PAUSE_KEY) === '1') return;
    } catch (e) {}
    if (timer) return;
    paused = false;
    onLight = typeof options.onLight === 'function' ? options.onLight : null;
    document.addEventListener('visibilitychange', onVisible);
    timer = window.setInterval(tick, 20000);
    tick();
}
