window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    loadTarget: function(target, options = {}) {
        if (!target) return;
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            return;
        }
        const normalized = YM.normalizeUrl(target);
        this.ignoreNextLoad = !!options.fromPush;

        // При загрузке сайта скрываем фоновое видео
        if (YM.background) YM.background.hide();

        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalized)}`;
    },

    clear: function() {
        YM.elements.iframe.src = 'about:blank';
        this.ignoreNextLoad = false;

        // При возврате на главную показываем видео
        if (YM.background) YM.background.show();
    },

    handleLoad: function() {
        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let actualTarget = null;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                actualTarget = urlParams.get('target');
            } else if (currentIframeSrc === 'about:blank') {
                // Если загружен about:blank, убеждаемся, что видео показано (на случай, если clear не был вызван)
                if (YM.background) YM.background.show();
                YM.elements.input.value = '';
                YM.panel.updateValidity();
                return;
            } else {
                actualTarget = currentIframeSrc;
            }

            if (!actualTarget) return;

            const normalizedActual = YM.normalizeUrl(actualTarget);

            // Обновляем поле ввода
            YM.elements.input.value = YM.simplifyUrl(normalizedActual);
            YM.panel.updateValidity();

            const currentUrlTarget = YM.getTargetFromUrl();

            if (this.ignoreNextLoad) {
                this.ignoreNextLoad = false;
                if (normalizedActual !== currentUrlTarget) {
                    YM.history.replaceCurrent(normalizedActual);
                }
            } else {
                if (normalizedActual !== currentUrlTarget) {
                    YM.history.replaceCurrent(normalizedActual);
                }
            }
        } catch (e) {
            console.warn('Ошибка в handleLoad', e);
        }
    },

    handleError: function() {
        console.warn('Не удалось загрузить сайт в iframe.');
        // При ошибке показываем фоновое видео и очищаем поле ввода
        if (YM.background) YM.background.show();
        YM.elements.input.value = '';
        YM.panel.updateValidity();
    },

    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        YM.history.push(url);
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
            YM.history.push(normalizedTarget);
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});