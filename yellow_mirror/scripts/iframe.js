// yellow_mirror/scripts/iframe.js
window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    /**
     * Загружает целевой URL в iframe.
     * options.fromHistory: true если вызов из popstate (не нужно менять историю)
     */
    loadTarget: function(target, options = {}) {
        if (!target) return;

        // Игнорируем служебные схемы
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            return;
        }

        const normalizedTarget = YM.normalizeUrl(target);
        // Если вызов не из истории, то предполагаем, что navigateTo уже вызвал pushState
        // и мы должны игнорировать следующий load
        if (!options.fromHistory) {
            this.ignoreNextLoad = true;
        }
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    clear: function() {
        YM.elements.iframe.src = 'about:blank';
        // Сбрасываем флаг, чтобы при загрузке about:blank ничего не делать
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
                // Главная страница
                this.ignoreNextLoad = false;
                YM.elements.input.value = '';
                YM.panel.updateValidity();
                return;
            } else {
                // Не проксированный URL (маловероятно)
                actualTarget = currentIframeSrc;
            }

            if (!actualTarget) return;

            const normalizedActual = YM.normalizeUrl(actualTarget);

            // Обновляем поле ввода
            YM.elements.input.value = YM.simplifyUrl(normalizedActual);
            YM.panel.updateValidity();

            // Если это загрузка, которую мы инициировали сами (ignoreNextLoad), то не синхронизируем историю
            if (this.ignoreNextLoad) {
                this.ignoreNextLoad = false;
                return;
            }

            // Иначе синхронизируем URL, если он не совпадает с текущим
            YM.history.syncIfNeeded(normalizedActual);
        } catch (e) {
            console.warn('Ошибка в handleLoad', e);
        }
    },

    handleError: function() {
        console.warn('Не удалось загрузить сайт в iframe.');
        // Можно показать сообщение, но пока просто логируем
    },

    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        YM.history.navigateTo(url);
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
            YM.history.navigateTo(normalizedTarget);
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});