window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    loadTarget: function(target) {
        if (!target) return;

        // Игнорируем служебные схемы
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            // Раньше тут был splash.show() — теперь ничего не делаем
            return;
        }

        const normalizedTarget = YM.normalizeUrl(target);
        this.ignoreNextLoad = false;
        // splash.show() удалён
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    handleLoad: function() {
        // splash.hide() удалён

        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let targetUrl = currentIframeSrc;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) targetUrl = target;
            } else {
                const urlObj = new URL(currentIframeSrc, window.location.origin);
                if (urlObj.protocol !== 'http:' && urlObj.protocol !== 'https:') {
                    return;
                }
            }

            setTimeout(() => {
                if (YM.iframe.ignoreNextLoad) {
                    YM.iframe.ignoreNextLoad = false;
                } else {
                    YM.pushBrowserUrl(targetUrl);
                }
            }, 0);
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
        }
    },

    handleError: function() {
        // splash.hide() удалён
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    },

    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        YM.iframe.loadTarget(url);
    }
};

window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'iframe-navigation') {
        const frameUrl = event.data.url;
        try {
            let targetUrl = frameUrl;
            if (frameUrl.includes('/api/')) {
                const urlObj = new URL(frameUrl, window.location.origin);
                const target = urlObj.searchParams.get('target');
                if (target) targetUrl = target;
            }

            const normalizedTarget = YM.normalizeUrl(targetUrl);

            YM.elements.input.value = YM.simplifyUrl(normalizedTarget);
            YM.panel.updateValidity();

            YM.pushBrowserUrl(normalizedTarget);

            YM.iframe.ignoreNextLoad = true;
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});