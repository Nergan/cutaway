document.addEventListener('DOMContentLoaded', function() {
    YM.elements.input.addEventListener('input', YM.panel.updateValidity);

    YM.elements.expandedPanel.addEventListener('mouseover', (e) => {
        const target = e.target.closest('input, button');
        YM.panel.setHighlight(!(target && YM.panel.isInteractiveElement(target)));
    });
    YM.elements.expandedPanel.addEventListener('mouseout', (e) => {
        const related = e.relatedTarget;
        if (!related || !YM.elements.expandedPanel.contains(related)) {
            YM.panel.setHighlight(false);
        }
    });

    YM.elements.expandedPanel.addEventListener('click', (e) => {
        const target = e.target.closest('input, button');
        if (!(target && YM.panel.isInteractiveElement(target))) {
            YM.panel.collapse();
        }
    });

    YM.elements.minimizedBar.addEventListener('click', YM.panel.expand);
    YM.elements.button.addEventListener('click', () => {
        const url = YM.elements.input.value.trim();
        if (url) YM.stream.loadSite(url);
    });
    YM.elements.input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const url = YM.elements.input.value.trim();
            if (url) YM.stream.loadSite(url);
        }
    });

    YM.background.init();

    const initialTarget = YM.getTargetFromUrl();
    if (initialTarget) {
        YM.elements.input.value = YM.simplifyUrl(initialTarget);
        YM.panel.updateValidity();
        YM.stream.loadSite(initialTarget);
    } else {
        YM.background.show();
    }
});