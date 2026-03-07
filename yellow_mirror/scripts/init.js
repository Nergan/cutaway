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
    YM.elements.button.addEventListener('click', YM.navigator.loadSite);
    YM.elements.input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            YM.navigator.loadSite();
        }
    });

    document.addEventListener('click', function(e) {
        const link = e.target.closest('a');
        if (link && link.href && !link.target) {
            try {
                const currentUrl = new URL(window.location.href);
                const linkUrl = new URL(link.href, window.location.href);
                if (linkUrl.origin === currentUrl.origin && linkUrl.pathname === currentUrl.pathname && linkUrl.search === currentUrl.search) {
                    return;
                }
            } catch (e) {}
            e.preventDefault();
            YM.navigator.navigate(link.href);
        }
    });

    document.addEventListener('submit', function(e) {
        const form = e.target;
        e.preventDefault();
        YM.navigator.submitForm(form);
    });

    window.addEventListener('popstate', YM.history.onPopState);

    const initialTarget = YM.getTargetFromUrl();
    if (initialTarget) {
        const normalized = YM.normalizeUrl(initialTarget);
        YM.elements.input.value = YM.simplifyUrl(normalized);
        YM.panel.updateValidity();
        YM.navigator.load(normalized);
    } else {
        if (YM.background) YM.background.show();
        YM.elements.input.value = '';
        YM.panel.updateValidity();
    }
});