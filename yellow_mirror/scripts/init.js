document.addEventListener('DOMContentLoaded', function() {
    // Инициализация панели
    YM.panel.init();

    // Подсказка: если есть target в URL, мы уже на странице сайта,
    // поле ввода заполнено упрощённым URL (заполняется сервером при вставке панели).
    // Но сервер может не заполнить поле, поэтому пробуем извлечь из URL.
    const currentTarget = YM.getTargetFromUrl();
    if (currentTarget) {
        YM.elements.input.value = YM.simplifyUrl(currentTarget);
    } else {
        // На главной - показываем видео
        if (YM.background) YM.background.show();
    }

    // Валидация поля (всегда активно)
    YM.panel.updateValidity();

    // События панели
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

    YM.elements.minimizedBar.addEventListener('click', () => YM.panel.expand());
    YM.elements.button.addEventListener('click', () => YM.panel.navigateToUrl());
    YM.elements.input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            YM.panel.navigateToUrl();
        }
    });
});