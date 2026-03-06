// yellow_mirror/scripts/history.js
window.YM = window.YM || {};

YM.history = {
    /**
     * Переход на новый URL (добавляет запись в историю)
     */
    navigateTo: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return; // уже на месте

        // Обновляем URL через pushState
        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.pushState({ target: normalized }, '', url);

        // Загружаем сайт в iframe
        YM.iframe.loadTarget(normalized);
    },

    /**
     * Синхронизация URL с текущим содержимым iframe (без добавления записи)
     */
    syncWithIframe: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return;

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.replaceState({ target: normalized }, '', url);
    },

    /**
     * Обработка навигации по истории (popstate)
     */
    onPopState: function(event) {
        const target = YM.getTargetFromUrl();
        if (target) {
            // Загружаем сайт, соответствующий target
            YM.iframe.loadTarget(target);
        } else {
            // Возврат на главную
            YM.iframe.clear();
            YM.elements.input.value = '';
            YM.panel.updateValidity();
        }
    }
};