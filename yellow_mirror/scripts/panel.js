window.YM = window.YM || {};

YM.panel = {
    // Состояние
    isCollapsed: false,

    init: function() {
        this.loadState();
        this.updateView();
    },

    isInteractiveElement: function(el) {
        return el && (el.tagName === 'INPUT' || el.tagName === 'BUTTON');
    },

    setHighlight: function(enable) {
        YM.elements.expandedPanel.classList.toggle('panel-highlight', enable);
    },

    collapse: function() {
        this.isCollapsed = true;
        this.saveState();
        this.updateView();
    },

    expand: function() {
        this.isCollapsed = false;
        this.saveState();
        this.updateView();
    },

    updateView: function() {
        if (this.isCollapsed) {
            YM.elements.expandedPanel.classList.add('collapsed');
            YM.elements.minimizedBar.classList.add('visible');
        } else {
            YM.elements.minimizedBar.classList.remove('visible');
            YM.elements.expandedPanel.classList.remove('collapsed');
        }
    },

    saveState: function() {
        try {
            sessionStorage.setItem('ym_panel_collapsed', this.isCollapsed ? '1' : '0');
        } catch (e) {}
    },

    loadState: function() {
        try {
            const val = sessionStorage.getItem('ym_panel_collapsed');
            this.isCollapsed = val === '1';
        } catch (e) {
            this.isCollapsed = false;
        }
    },

    updateValidity: function() {
        // Всегда активная кнопка и белый текст
        YM.elements.button.disabled = false;
        YM.elements.input.classList.remove('invalid');
    },

    // Навигация на новый URL через прокси
    navigateToUrl: function() {
        const trimmed = YM.elements.input.value.trim();
        if (!trimmed) return;
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        // Перенаправляем браузер на прокси-эндпоинт
        window.location.href = '/api/?target=' + encodeURIComponent(url);
    }
};