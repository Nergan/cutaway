window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,
    errorShown: false,

    loadTarget: function(target) {
        if (!target) return;

        if (YM.isSelfAppUrl(target)) {
            window.location.href = target;
            return;
        }

        const normalizedTarget = YM.normalizeUrl(target);
        this.ignoreNextLoad = false;
        this.errorShown = false;
        YM.splash.show();
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    handleLoad: function() {
        YM.splash.hide();

        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let targetUrl = currentIframeSrc;
            let isProxied = false;

            // Если src содержит /api/ и параметр target, значит это прокси-запрос
            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) {
                    targetUrl = target;
                    isProxied = true;
                }
            }

            const currentHost = window.location.host;
            const iframeHost = new URL(currentIframeSrc).host;

            // Если iframe загрузил страницу с нашего домена, но это не прокси – ошибка
            if (iframeHost === currentHost && !isProxied) {
                this.showErrorAndReset();
                return;
            }

            // Обновляем URL в адресной строке только для успешных прокси-загрузок
            if (isProxied) {
                setTimeout(() => {
                    if (YM.iframe.ignoreNextLoad) {
                        YM.iframe.ignoreNextLoad = false;
                    } else {
                        YM.replaceBrowserUrl(targetUrl);
                    }
                }, 0);
            }
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
        }
    },

    handleError: function() {
        YM.splash.hide();
        this.showErrorAndReset();
    },

    showErrorAndReset: function() {
        if (this.errorShown) return;
        this.errorShown = true;
        YM.toast.show('Sorry, it is impossible to access the site', 5000);
        YM.elements.iframe.src = 'about:blank';
        // Не меняем URL в адресной строке
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

window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'iframe-navigation') {
        const frameUrl = event.data.url;
        try {
            let targetUrl = frameUrl;
            let isProxied = false;
            if (frameUrl.includes('/api/')) {
                const urlObj = new URL(frameUrl, window.location.origin);
                const target = urlObj.searchParams.get('target');
                if (target) {
                    targetUrl = target;
                    isProxied = true;
                }
            }

            const currentHost = window.location.host;
            const frameHost = new URL(frameUrl, window.location.origin).host;

            // Если навигация привела к странице нашего домена без прокси – ошибка
            if (frameHost === currentHost && !isProxied) {
                YM.iframe.showErrorAndReset();
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