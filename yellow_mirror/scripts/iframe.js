// yellow_mirror/scripts/iframe.js (фрагменты)
window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    loadTarget: function(target) {
        if (!target) return;

        // Игнорируем служебные схемы
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            return;
        }

        const normalizedTarget = YM.normalizeUrl(target);
        this.ignoreNextLoad = false;
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    clear: function() {
        // Очистить iframe (главная страница)
        YM.elements.iframe.src = 'about:blank';
    },

    handleLoad: function() {
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
                    return; // не обновляем историю для about:blank и т.п.
                }
            }

            // Синхронизируем URL, если это не внутренний переход
            if (!this.ignoreNextLoad) {
                YM.history.syncWithIframe(targetUrl);
            } else {
                this.ignoreNextLoad = false;
            }

            // Обновляем поле ввода
            YM.elements.input.value = YM.simplifyUrl(targetUrl);
            YM.panel.updateValidity();
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
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
        // Используем navigateTo для добавления записи
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

            // Внутренняя навигация — добавляем запись в историю
            YM.history.navigateTo(normalizedTarget);

            // Предотвращаем двойную обработку в handleLoad
            YM.iframe.ignoreNextLoad = true;
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});