// yellow_mirror/scripts/history.js
window.YM = window.YM || {};

YM.history = {
    /**
     * Переход на новый URL (вызывается при вводе или клике по ссылке)
     */
    navigateTo: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return; // уже на месте

        // Создаём новый URL с target
        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        
        // Добавляем запись в историю
        window.history.pushState({ target: normalized }, '', url);
        
        // Загружаем iframe с пометкой, что это навигация (установим ignoreNextLoad)
        YM.iframe.loadTarget(normalized, { fromHistory: false });
    },

    /**
     * Синхронизация URL с текущим содержимым iframe (при необходимости)
     */
    syncIfNeeded: function(actualTarget) {
        if (!actualTarget) return;
        const normalized = YM.normalizeUrl(actualTarget);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return;

        // Заменяем текущую запись, чтобы URL соответствовал фактическому содержимому
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
            // Загружаем соответствующий сайт (без добавления в историю)
            YM.iframe.loadTarget(target, { fromHistory: true });
        } else {
            // Возврат на главную
            YM.iframe.clear();
            YM.elements.input.value = '';
            YM.panel.updateValidity();
        }
    }
};