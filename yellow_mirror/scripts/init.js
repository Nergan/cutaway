// yellow_mirror/scripts/init.js
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
    YM.elements.button.addEventListener('click', YM.iframe.loadSite);
    YM.elements.input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            YM.iframe.loadSite();
        }
    });

    YM.elements.iframe.addEventListener('load', () => YM.iframe.handleLoad());
    YM.elements.iframe.addEventListener('error', () => YM.iframe.handleError());

    // Обработка навигации по истории
    window.addEventListener('popstate', YM.history.onPopState);

    // Инициализация из URL
    const initialTarget = YM.getTargetFromUrl();
    if (initialTarget) {
        const normalized = YM.normalizeUrl(initialTarget);
        YM.elements.input.value = YM.simplifyUrl(normalized);
        YM.panel.updateValidity();
        // Загружаем, но не добавляем запись (replaceState при необходимости)
        YM.iframe.loadTarget(normalized);
        // Синхронизируем URL (на случай, если он не совпадает)
        YM.history.syncWithIframe(normalized);
    } else {
        // Главная страница
        YM.iframe.clear();
        YM.elements.input.value = '';
        YM.panel.updateValidity();
    }
});