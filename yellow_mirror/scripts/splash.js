window.YM = window.YM || {};

YM.splash = {
    init: function() {
        // Сохраняем ссылки на слои, если нужно (но необязательно)
        this.layers = document.querySelectorAll('.splash-layer');
    },

    show: function() {
        const el = YM.elements.splash;
        const iframe = YM.elements.iframe;
        if (!el || !iframe) return;
        el.style.display = 'block';
        iframe.style.pointerEvents = 'none';
        // Убраны все анимации и отслеживание мыши
    },

    hide: function() {
        const el = YM.elements.splash;
        const iframe = YM.elements.iframe;
        if (!el || !iframe) return;
        el.style.display = 'none';
        iframe.style.pointerEvents = 'auto';
        // Убрана остановка трекинга
    }
};

document.addEventListener('DOMContentLoaded', () => {
    YM.splash.init();
});