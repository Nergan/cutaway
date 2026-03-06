// Инициализация после загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    // Не устанавливаем src для iframe — пусть остаётся пустым, сплэш перекроет

    // Привязываем обработчики к элементам
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

    window.addEventListener('popstate', () => {
        const target = YM.getTargetFromUrl();
        if (target) {
            YM.iframe.loadTarget(target);
        } else {
            // Возврат на главную: показываем сплэш, НЕ меняем iframe
            YM.splash.show();
            YM.elements.input.value = '';
            YM.panel.updateValidity();
        }
    });

    // Инициализация из URL
    const initialTarget = YM.getTargetFromUrl();
    if (initialTarget) {
        // Убрана проверка на внутренний путь приложения
        const normalized = YM.normalizeUrl(initialTarget);
        YM.elements.input.value = YM.simplifyUrl(normalized);
        YM.panel.updateValidity();
        YM.iframe.loadTarget(normalized);
    } else {
        // Если target нет, показываем сплэш (фон стартовой страницы)
        YM.splash.show();
    }
});