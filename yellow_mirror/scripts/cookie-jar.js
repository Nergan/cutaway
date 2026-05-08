// yellow_mirror/scripts/cookie-jar.js
'use strict';

(function (global) {
  const DB_NAME = 'ym-cookie-jar';
  const DB_VERSION = 1;
  const STORE_NAME = 'cookies';

  class CookieJar {
    constructor() {
      this._dbPromise = null;
    }

    /** Return a promise that resolves to the database instance. */
    _openDB() {
      if (this._dbPromise) return this._dbPromise;

      this._dbPromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = (event) => {
          const db = event.target.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            // Key: domain name
            db.createObjectStore(STORE_NAME, { keyPath: 'domain' });
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return this._dbPromise;
    }

    /**
     * Get the stored cookie string for a given domain.
     * @param {string} domain
     * @returns {Promise<string>} A promise that resolves to the full cookie string (or '').
     */
    async getCookies(domain) {
      const db = await this._openDB();
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const request = store.get(domain);
      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          resolve(request.result ? request.result.cookie : '');
        };
        request.onerror = () => reject(request.error);
      });
    }

    /**
     * Set (overwrite) the full cookie string for a domain.
     * This replaces any previously stored cookie for that domain.
     */
    async setCookies(domain, cookieString) {
      const db = await this._openDB();
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      return new Promise((resolve, reject) => {
        store.put({ domain, cookie: cookieString });
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }

    /**
     * Merge a single Set-Cookie header value into the jar for the domain.
     * This simplistic merge adds the new cookie to the existing string.
     * A production version would parse cookies properly and handle expiry.
     */
    async mergeSetCookieHeader(domain, setCookieValue) {
      if (!setCookieValue) return;
      const current = await this.getCookies(domain);
      // Append the new cookie (separated by "; ")
      const updated = current ? `${current}; ${setCookieValue}` : setCookieValue;
      await this.setCookies(domain, updated);
    }

    /**
     * Read all Set-Cookie headers from a fetch response headers object and store them.
     */
    async storeSetCookieHeaders(domain, headers) {
      // Headers can have multiple Set-Cookie (but the simple Headers object merges them with ',').
      // For simplicity we treat the whole header as a string and append it.
      const setCookie = headers.get('Set-Cookie');
      if (setCookie) {
        await this.mergeSetCookieHeader(domain, setCookie);
      }
    }
  }

  // Expose a singleton globally so the service worker can use it.
  global.cookieJar = new CookieJar();
})(self);