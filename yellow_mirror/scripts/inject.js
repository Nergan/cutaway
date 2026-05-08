(function() {
    // 1. Framebust Defeat
    try {
        if (window !== window.top) {
            Object.defineProperty(window, 'top', { value: window, writable: false });
            Object.defineProperty(window, 'parent', { value: window, writable: false });
        }
    } catch (e) {}

    // 2. Intercept Fetch API natively
    const origFetch = window.fetch;
    window.fetch = async function(resource, options) {
        let url = resource instanceof Request ? resource.url : resource;
        if (typeof url === 'string' && (url.startsWith('http://') || url.startsWith('https://')) && !url.includes('/yellow-mirror/proxy/')) {
            url = '/yellow-mirror/proxy/' + url;
            if (resource instanceof Request) {
                resource = new Request(url, options || resource);
            } else {
                resource = url;
            }
        }
        return origFetch.call(this, resource, options);
    };

    // 3. Intercept XHR natively
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
        if (typeof url === 'string' && (url.startsWith('http://') || url.startsWith('https://')) && !url.includes('/yellow-mirror/proxy/')) {
            url = '/yellow-mirror/proxy/' + url;
        }
        return origOpen.call(this, method, url, async, user, password);
    };

    // 4. Intercept Web Workers (Fixes some Twitch/SPA issues)
    const origWorker = window.Worker;
    window.Worker = function(scriptURL, options) {
        if (typeof scriptURL === 'string' && (scriptURL.startsWith('http://') || scriptURL.startsWith('https://')) && !scriptURL.includes('/yellow-mirror/proxy/')) {
            scriptURL = '/yellow-mirror/proxy/' + scriptURL;
        }
        return new origWorker(scriptURL, options);
    };

    // History syncing
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
    history.pushState = function() { origPush.apply(this, arguments); syncUrl(); };

    const origReplace = history.replaceState;
    history.replaceState = function() { origReplace.apply(this, arguments); syncUrl(); };

    window.addEventListener('popstate', syncUrl);
    window.addEventListener('hashchange', syncUrl);

    const origOpenWindow = window.open;
    window.open = function(url, target, features) {
        if (url && (url.startsWith('http://') || url.startsWith('https://'))) url = '/yellow-mirror/proxy/' + url;
        return origOpenWindow.call(window, url, target, features);
    };

    syncUrl();
})();