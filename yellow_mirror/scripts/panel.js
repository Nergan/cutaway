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
        const trimmed = YM.elements.input.value.trim();
        const valid = YM.isValidUrl(trimmed) && !YM.isSelfUrl(trimmed);
        YM.elements.button.disabled = !valid;
        YM.elements.input.classList.toggle('invalid', !valid);
    }
};

