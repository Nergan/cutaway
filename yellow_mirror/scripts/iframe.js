window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    /**
     * Загружает целевой URL в iframe.
     * options.fromPush: true если вызов из push (будет игнорировать следующий load для проверки редиректа)
     * options.fromPop: true если вызов из popstate (не игнорирует load)
     */
    loadTarget: function(target, options = {}) {
        if (!target) return;
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            return;
        }
        const normalized = YM.normalizeUrl(target);
        // Устанавливаем ignoreNextLoad только при push
        this.ignoreNextLoad = !!options.fromPush;
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalized)}`;
    },

    clear: function() {
        YM.elements.iframe.src = 'about:blank';
        this.ignoreNextLoad = false;
    },

    handleLoad: function() {
        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let actualTarget = null;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                actualTarget = urlParams.get('target');
            } else if (currentIframeSrc === 'about:blank') {
                this.ignoreNextLoad = false;
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
                // Это загрузка после нашего pushState
                this.ignoreNextLoad = false;
                if (normalizedActual !== currentUrlTarget) {
                    // Произошёл редирект — заменяем текущую запись
                    YM.history.replaceCurrent(normalizedActual);
                }
                // Если совпадают, ничего не делаем
            } else {
                // Это загрузка после popstate или другой (например, перезагрузка страницы)
                if (normalizedActual !== currentUrlTarget) {
                    // Несоответствие из-за редиректа — заменяем текущую запись
                    YM.history.replaceCurrent(normalizedActual);
                }
            }
        } catch (e) {
            console.warn('Ошибка в handleLoad', e);
        }
    },

    handleError: function() {
        console.warn('Не удалось загрузить сайт в iframe.');
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

// Обработка сообщений от iframe (внутренняя навигация)
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
            // Это внутренняя навигация — добавляем запись в историю
            YM.history.push(normalizedTarget);
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});