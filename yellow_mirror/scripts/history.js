window.YM = window.YM || {};

YM.history = {
    /**
     * Добавить новую запись в историю и перейти по target
     */
    push: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return; // уже на месте

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.pushState({ target: normalized }, '', url);

        // Загружаем iframe с пометкой, что это push
        YM.iframe.loadTarget(normalized, { fromPush: true });
    },

    /**
     * Заменить текущую запись истории на новый target (без перезагрузки iframe)
     * Используется при редиректах
     */
    replaceCurrent: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return;

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.replaceState({ target: normalized }, '', url);
    },

    /**
     * Обработчик popstate (навигация по истории)
     */
    onPopState: function(event) {
        const target = YM.getTargetFromUrl();
        if (target) {
            // Загружаем iframe, указывая, что это popstate (не добавляем запись)
            YM.iframe.loadTarget(target, { fromPop: true });
        } else {
            // Возврат на главную
            YM.iframe.clear();
            YM.elements.input.value = '';
            YM.panel.updateValidity();
        }
    }
};