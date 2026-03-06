window.YM = window.YM || {};

YM.iframe = {
    lastLoadTime: 0, // время последней успешной загрузки iframe

    /**
     * Загрузить целевой URL в iframe
     */
    loadTarget: function(target, options = {}) {
        if (!target) return;
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) return;
        const normalized = YM.normalizeUrl(target);
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalized)}`;
    },

    /**
     * Очистить iframe (главная страница)
     */
    clear: function() {
        YM.elements.iframe.src = 'about:blank';
    },

    /**
     * Обработчик успешной загрузки iframe
     */
    handleLoad: function() {
        this.lastLoadTime = Date.now();
        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let actualTarget = null;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                actualTarget = urlParams.get('target');
            } else if (currentIframeSrc === 'about:blank') {
                YM.elements.input.value = '';
                YM.panel.updateValidity();
                return;
            } else {
                actualTarget = currentIframeSrc;
            }

            if (!actualTarget) return;

            const normalizedActual = YM.normalizeUrl(actualTarget);
            YM.elements.input.value = YM.simplifyUrl(normalizedActual);
            YM.panel.updateValidity();

            const currentUrlTarget = YM.getTargetFromUrl();
            if (normalizedActual !== currentUrlTarget) {
                // Произошёл редирект или несоответствие – исправляем текущую запись
                YM.history.replaceCurrent(normalizedActual);
            }
        } catch (e) {
            console.warn('Ошибка в handleLoad', e);
        }
    },

    /**
     * Обработчик ошибки загрузки iframe
     */
    handleError: function() {
        console.warn('Не удалось загрузить сайт в iframe.');
    },

    /**
     * Загрузить сайт из поля ввода (вызывается по кнопке или Enter)
     */
    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        // Пользовательский ввод – всегда push
        YM.history.push(url);
        YM.iframe.loadTarget(url);
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
            const timeSinceLastLoad = Date.now() - YM.iframe.lastLoadTime;

            // Эвристика: если сообщение пришло менее чем через 1 секунду после загрузки,
            // считаем это автоматическим редиректом и заменяем текущую запись,
            // иначе – пользовательское действие, добавляем запись.
            if (timeSinceLastLoad < 1000) {
                YM.history.replaceCurrent(normalizedTarget);
            } else {
                YM.history.push(normalizedTarget);
            }

            // Обновляем поле ввода сразу (на случай, если сообщение пришло до handleLoad)
            YM.elements.input.value = YM.simplifyUrl(normalizedTarget);
            YM.panel.updateValidity();
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});