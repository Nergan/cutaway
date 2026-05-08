importScripts('/yellow_mirror/scripts/cookie-jar.js');

// yellow_mirror/scripts/sw.js
const API_PATH_PREFIX = '/yellow-mirror/api/';
const CACHE_NAME = 'ym-proxy-v1';

// ------------------------------------------------------------------
self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
});

// ------------------------------------------------------------------
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only handle requests to our proxy endpoint
  if (!url.pathname.startsWith(API_PATH_PREFIX)) return;

  event.respondWith(handleProxyRequest(event.request));
});

// ------------------------------------------------------------------
async function handleProxyRequest(request) {
  const url = new URL(request.url);
  const target = url.searchParams.get('target');
  if (!target) {
    return new Response('Missing target', { status: 400 });
  }

  // --- Forward to our own backend (same path) ---
  const proxyUrl = self.location.origin + API_PATH_PREFIX + '?target=' + encodeURIComponent(target);
  // We can use the original method, headers, body, but careful with headers.
  // Remove unwanted headers, attach custom cookie from jar.
  const headers = new Headers(request.headers);
  // Remove host, referer, etc. that might confuse the backend.
  headers.delete('host');
  headers.delete('referer');
  headers.delete('origin');

  // Attach stored cookies for the target domain
  const targetDomain = new URL(target).hostname;
  const jarCookies = await cookieJar.getCookies(targetDomain);
  if (jarCookies) {
    headers.set('Cookie', jarCookies);
  }

  const proxyRequest = new Request(proxyUrl, {
    method: request.method,
    headers: headers,
    body: request.body,
    redirect: 'manual'   // we handle redirects manually
  });

  let response;
  try {
    response = await fetch(proxyRequest);
  } catch (err) {
    return new Response('Proxy fetch failed', { status: 502 });
  }

  // --- Handle redirects: store cookies, follow manually ---
  let redirectCount = 0;
  const MAX_REDIRECTS = 10;
  while (response.status >= 301 && response.status <= 308 && response.headers.has('Location')) {
    if (++redirectCount > MAX_REDIRECTS) {
      return new Response('Too many redirects', { status: 502 });
    }
    // Store Set-Cookie headers from this redirect response
    await cookieJar.storeSetCookieHeaders(targetDomain, response.headers);

    const location = response.headers.get('Location');
    // location is already a full proxy URL (e.g. /yellow-mirror/api/?target=...)
    response = await fetch(location, {
      method: 'GET',   // strict redirect following
      headers: headers,
      redirect: 'manual'
    });
  }

  // Store cookies from the final response
  await cookieJar.storeSetCookieHeaders(targetDomain, response.headers);

  // --- If HTML, rewrite URLs and inject interceptor ---
  const contentType = response.headers.get('Content-Type') || '';
  if (contentType.includes('text/html')) {
    let html = await response.text();
    html = rewriteHtmlUrls(html, target);
    html = injectInterceptor(html);
    return new Response(html, {
      status: response.status,
      headers: stripSetCookieHeaders(response.headers)
    });
  } else {
    // For non-HTML, just return the response as-is (strip Set-Cookie)
    return new Response(response.body, {
      status: response.status,
      headers: stripSetCookieHeaders(response.headers)
    });
  }
}

// ------------------------------------------------------------------
// URL rewriting inside HTML (client‑side)
function rewriteHtmlUrls(html, baseTarget) {
  // Use a simple regex to catch common attributes.
  // In production, use a proper DOM parser.
  const proxyBase = self.location.origin + API_PATH_PREFIX;
  const baseUrl = baseTarget;

  // Rewrite href/src/action attributes
  function replacer(match, prefix, url) {
    if (!url || url.startsWith('#') || url.startsWith('data:')) return match;
    try {
      const absolute = new URL(url, baseUrl).href;
      return prefix + '="' + proxyBase + '?target=' + encodeURIComponent(absolute) + '"';
    } catch (e) {
      return match;
    }
  }

  html = html.replace(/(href|src|action)="([^"]*)"/gi, replacer);
  html = html.replace(/(href|src|action)='([^']*)'/gi, replacer);
  return html;
}

// ------------------------------------------------------------------
// Inject the DOM‑interceptor script as the FIRST element in <head>
function injectInterceptor(html) {
  const interceptorScript = `<script src="${self.location.origin}/yellow_mirror/scripts/dom-interceptor.js"></script>`;
  // Insert right after <head> or before <html> if no head
  html = html.replace(/(<head[^>]*>)/i, '$1' + interceptorScript);
  if (!/<head/i.test(html)) {
    html = '<head>' + interceptorScript + '</head>' + html;
  }
  return html;
}

// ------------------------------------------------------------------
// Remove Set-Cookie headers to prevent polluting our domain
function stripSetCookieHeaders(headers) {
  const newHeaders = new Headers(headers);
  newHeaders.delete('Set-Cookie');
  return newHeaders;
}

// ------------------------------------------------------------------
// Cookie jar helpers (IndexedDB based)
class CookieJar {
  constructor() {
    this.dbPromise = indexedDB.open('ym-cookie-jar', 1);
    this.dbPromise.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('cookies')) {
        db.createObjectStore('cookies', { keyPath: 'domain' });
      }
    };
  }

  async getDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('ym-cookie-jar', 1);
      request.onsuccess = (e) => resolve(e.target.result);
      request.onerror = reject;
    });
  }

  async getCookies(domain) {
    const db = await this.getDB();
    return new Promise((resolve) => {
      const tx = db.transaction('cookies', 'readonly');
      const store = tx.objectStore('cookies');
      const req = store.get(domain);
      req.onsuccess = () => resolve(req.result ? req.result.cookie : '');
    });
  }

  async setCookies(domain, cookieString) {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('cookies', 'readwrite');
      const store = tx.objectStore('cookies');
      store.put({ domain, cookie: cookieString });
      tx.oncomplete = resolve;
      tx.onerror = reject;
    });
  }

  async storeSetCookieHeaders(domain, headers) {
    const setCookie = headers.get('Set-Cookie');
    if (!setCookie) return;
    // Simple merge: add new cookie; full cookie jar logic would be more complex
    let current = await this.getCookies(domain);
    current += '; ' + setCookie;
    await this.setCookies(domain, current);
  }
}
const cookieJar = new CookieJar();