window.YM = window.YM || {};
YM.iframe = {
    ignoreNextLoad: false,

    loadTarget: function(target, options = {}) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        this.ignoreNextLoad = !!options.fromPush;
        if (YM.background) YM.background.hide();
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalized)}`;
    },

    clear: function() {
        YM.elements.iframe.src = 'about:blank';
        this.ignoreNextLoad = false;
        if (YM.background) YM.background.show();
    },

    handleLoad: function() {
        try {
            // Not needed – history sync done via messages from interceptor
        } catch(e) { console.warn(e); }
    },

    loadSite: function() {
        let url = YM.elements.input.value.trim();
        if (!url.match(/^https?:\/\//i)) url = 'https://' + url;
        YM.history.push(url);
    }
};

window.addEventListener('message', (event) => {
    if (!event.data || !event.data.type) return;
    if (event.data.type === 'iframe-push' || event.data.type === 'iframe-replace') {
        const frameUrl = event.data.url;
        try {
            let targetUrl = frameUrl;
            if (frameUrl.includes('/api/')) {
                const urlObj = new URL(frameUrl, window.location.origin);
                const target = urlObj.searchParams.get('target');
                if (target) targetUrl = target;
            }
            const normalized = YM.normalizeUrl(targetUrl);
            if (event.data.type === 'iframe-push') {
                YM.history.push(normalized);
            } else {
                YM.history.replaceCurrent(normalized);
            }
        } catch(e) { console.warn(e); }
    }
});