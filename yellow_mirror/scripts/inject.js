(function() {
    function getRealUrl() {
        let pathStr = window.location.pathname;
        if(pathStr.startsWith('/yellow-mirror/proxy/')) {
            return pathStr.substring(21) + window.location.search + window.location.hash;
        }
        return window.location.href;
    }

    function syncUrl() {
        window.parent.postMessage({ type: 'ym-nav', url: getRealUrl() }, '*');
    }

    // Hook PushState
    const origPush = history.pushState;
    history.pushState = function() {
        origPush.apply(this, arguments);
        syncUrl();
    };

    // Hook ReplaceState
    const origReplace = history.replaceState;
    history.replaceState = function() {
        origReplace.apply(this, arguments);
        syncUrl();
    };

    window.addEventListener('popstate', syncUrl);
    window.addEventListener('hashchange', syncUrl);

    // Trap new tabs inside the proxy
    const origOpen = window.open;
    window.open = function(url, target, features) {
        if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
            url = '/yellow-mirror/proxy/' + url;
        }
        return origOpen.call(window, url, target, features);
    };

    syncUrl();
})();