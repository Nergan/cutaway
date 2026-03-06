window.YM = window.YM || {};

YM.panel = {
    isInteractiveElement: function(el) {
        return el && (el.tagName === 'INPUT' || el.tagName === 'BUTTON');
    },

    setHighlight: function(enable) {
        YM.elements.expandedPanel.classList.toggle('panel-highlight', enable);
    },

    collapse: function() {
        YM.elements.expandedPanel.classList.add('collapsed');
        YM.elements.minimizedBar.classList.add('visible');
    },

    expand: function() {
        YM.elements.minimizedBar.classList.remove('visible');
        YM.elements.expandedPanel.classList.remove('collapsed');
    },

    updateValidity: function() {
        // Всегда активная кнопка и белый текст (убраны проверки)
        YM.elements.button.disabled = false;
        YM.elements.input.classList.remove('invalid'); // убираем красный цвет, если был
    }
};