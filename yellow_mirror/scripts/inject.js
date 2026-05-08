(function() {
    // FIX: Defeat YouTube/Google Framebusting.
    // We trick the SPA into thinking it is NOT inside an iframe.
    try {
        if (window !== window.top) {
            Object.defineProperty(window, 'top', { value: window, writable: false });
            Object.defineProperty(window, 'parent', { value: window, writable: false });
        }
    } catch (e) { console.warn("Framebust block failed", e); }

    function getRealUrl() {
        let pathStr = window.location.pathname;
        if(pathStr.includes('/proxy/')) {
            let target = pathStr.split('/proxy/')[1] + window.location.search + window.location.hash;
            return target.replace(/^(https?:)\/+(.*)/, "$1//$2");
        }
        return window.location.href;
    }

    function syncUrl() {
        window.parent.postMessage({ type: 'ym-nav', url: getRealUrl() }, '*');
    }

    const origPush = history.pushState;
    history.pushState = function() {
        origPush.apply(this, arguments);
        syncUrl();
    };

    const origReplace = history.replaceState;
    history.replaceState = function() {
        origReplace.apply(this, arguments);
        syncUrl();
    };

    window.addEventListener('popstate', syncUrl);
    window.addEventListener('hashchange', syncUrl);

    const origOpen = window.open;
    window.open = function(url, target, features) {
        if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
            url = '/yellow-mirror/proxy/' + url;
        }
        return origOpen.call(window, url, target, features);
    };

    // Override document.domain natively if possible to help reCAPTCHA
    try {
        const parsedTarget = new URL(getRealUrl());
        Object.defineProperty(document, 'domain', {
            get: () => parsedTarget.hostname,
            set: (v) => { /* ignore */ }
        });
    } catch (e) {}

    syncUrl();
})();