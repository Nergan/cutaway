window.YM = window.YM || {};

YM.history = {
    /**
     * Добавить новую запись в историю (pushState)
     */
    push: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const current = YM.getTargetFromUrl();
        if (normalized === current) return;

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.pushState({ target: normalized }, '', url);
    },

    /**
     * Заменить текущую запись в истории (replaceState)
     */
    replaceCurrent: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const current = YM.getTargetFromUrl();
        if (normalized === current) return;

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.replaceState({ target: normalized }, '', url);
    },

    /**
     * Обработчик события popstate (навигация по истории)
     */
    onPopState: function(event) {
        const target = YM.getTargetFromUrl();
        if (target) {
            YM.iframe.loadTarget(target, { fromPop: true });
        } else {
            YM.iframe.clear();
            YM.elements.input.value = '';
            YM.panel.updateValidity();
        }
    }
};