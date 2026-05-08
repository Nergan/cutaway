(function() {
    function getRealUrl() {
        let pathStr = window.location.pathname;
        if(pathStr.includes('/proxy/')) {
            let target = pathStr.split('/proxy/')[1] + window.location.search + window.location.hash;
            return target.replace(/^(https?:)\/+(.*)/, "$1//$2"); // Fix missing slashes
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

    // Stop links opening in outside tabs
    const origOpen = window.open;
    window.open = function(url, target, features) {
        if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
            url = '/yellow-mirror/proxy/' + url;
        }
        return origOpen.call(window, url, target, features);
    };

    syncUrl();
})();