window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    loadTarget: function(target) {
        if (!target) return;

        if (YM.isSelfAppUrl(target)) {
            window.location.href = target;
            return;
        }

        // Блокировка для startpage.com
        try {
            const urlObj = new URL(target);
            if (urlObj.hostname.includes('startpage.com')) {
                // Только показываем сообщение, НЕ скрываем сплэш, НЕ меняем iframe
                YM.showBlockedMessage();
                return;
            }
        } catch (e) {
            // Некорректный URL — дальше проверит isValidUrl
        }

        const normalizedTarget = YM.normalizeUrl(target);
        this.ignoreNextLoad = false;
        YM.splash.show();
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    handleLoad: function() {
        YM.splash.hide();

        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let targetUrl = currentIframeSrc;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) targetUrl = target;
            }

            if (YM.isSelfAppUrl(targetUrl)) {
                window.location.href = targetUrl;
                return;
            }

            setTimeout(() => {
                if (YM.iframe.ignoreNextLoad) {
                    YM.iframe.ignoreNextLoad = false;
                } else {
                    YM.replaceBrowserUrl(targetUrl);
                }
            }, 0);
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
        }
    },

    handleError: function() {
        YM.splash.hide();
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    },

    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        if (!YM.isValidUrl(trimmed) || YM.isSelfUrl(trimmed)) return;

        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        YM.iframe.loadTarget(url);
    }
};

YM.showBlockedMessage = function() {
    const msgEl = document.getElementById('error-message');
    if (!msgEl) return;
    // НЕ скрываем сплэш — оставляем фон стартовой страницы
    msgEl.classList.remove('hidden');
    setTimeout(() => {
        msgEl.classList.add('hidden');
    }, 5000);
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

            if (YM.isSelfAppUrl(targetUrl)) {
                window.location.href = targetUrl;
                return;
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