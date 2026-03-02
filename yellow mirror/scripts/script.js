(function() {
    // ---------- Элементы DOM ----------
    const expandedPanel = document.getElementById('expandedPanel');
    const minimizedBar = document.getElementById('minimizedBar');
    const input = document.getElementById('url-input');
    const button = document.getElementById('load-site-btn');
    const iframe = document.getElementById('site-frame');
    const splash = document.getElementById('splash');
    const splashLayer = document.querySelector('.splash-layer');

    // Переменные для анимации движения слоя
    let targetX = 0, targetY = 0;
    let currentX = 0, currentY = 0;
    let rafId = null;
    const maxOffset = 25; // максимальное смещение в процентах

    // ---------- Управление заглушкой и iframe ----------
    function showSplash() {
        splash.style.display = 'block';
        // Отключаем pointer-events на iframe, чтобы мышь проходила сквозь него
        iframe.style.pointerEvents = 'none';
        startMouseTracking();
    }

    function hideSplash() {
        splash.style.display = 'none';
        // Возвращаем iframe интерактивность
        iframe.style.pointerEvents = 'auto';
        stopMouseTracking();
    }

    // При старте показываем заглушку
    showSplash();

    // Скрываем при успешной загрузке или ошибке
    iframe.addEventListener('load', hideSplash);
    iframe.addEventListener('error', hideSplash);

    // ---------- Отслеживание мыши для движения слоя ----------
    function handleMouseMove(e) {
        if (!splashLayer || splash.style.display === 'none') return;

        // Нормализованные координаты от -1 до 1 (центр экрана = 0)
        const x = (e.clientX / window.innerWidth) * 2 - 1;
        const y = (e.clientY / window.innerHeight) * 2 - 1;

        // Инвертируем направление: слой движется в противоположную сторону от мыши
        targetX = -x * maxOffset;
        targetY = -y * maxOffset;
    }

    function updateLayerTransform() {
        if (!splashLayer || splash.style.display === 'none') return;

        // Плавное приближение к цели
        currentX += (targetX - currentX) * 0.1;
        currentY += (targetY - currentY) * 0.1;

        splashLayer.style.transform = `translate(${currentX}%, ${currentY}%)`;

        rafId = requestAnimationFrame(updateLayerTransform);
    }

    function startMouseTracking() {
        // Используем document, чтобы ловить события, проходящие через iframe с pointer-events: none
        document.addEventListener('mousemove', handleMouseMove);
        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(updateLayerTransform);
    }

    function stopMouseTracking() {
        document.removeEventListener('mousemove', handleMouseMove);
        if (rafId) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
        // Сброс позиции слоя при скрытии
        if (splashLayer) {
            splashLayer.style.transform = 'translate(0%, 0%)';
        }
        currentX = 0; currentY = 0; targetX = 0; targetY = 0;
    }

    // Обработка изменения размера окна
    window.addEventListener('resize', () => {
        targetX = 0;
        targetY = 0;
    });

    // ---------- Валидация URL ----------
    function isValidUrl(str) {
        const trimmed = str.trim();
        if (trimmed === '' || /\s/.test(trimmed)) return false;
        const urlPattern = /^(https?:\/\/)?([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(:\d+)?(\/[^\s]*)?(\?[^\s]*)?(\#[^\s]*)?$/;
        return urlPattern.test(trimmed);
    }

    function updateValidity() {
        const valid = isValidUrl(input.value);
        button.disabled = !valid;
        input.classList.toggle('invalid', !valid);
    }

    input.addEventListener('input', updateValidity);
    updateValidity();

    // ---------- Подсветка панели ----------
    function isInteractiveElement(el) {
        return el && (el.tagName === 'INPUT' || el.tagName === 'BUTTON');
    }

    function setPanelHighlight(enable) {
        expandedPanel.classList.toggle('panel-highlight', enable);
    }

    expandedPanel.addEventListener('mouseover', (e) => {
        const target = e.target.closest('input, button');
        setPanelHighlight(!(target && isInteractiveElement(target)));
    });

    expandedPanel.addEventListener('mouseout', (e) => {
        const related = e.relatedTarget;
        if (!related || !expandedPanel.contains(related)) {
            setPanelHighlight(false);
        }
    });

    // ---------- Сворачивание / разворачивание ----------
    function collapsePanel() {
        expandedPanel.classList.add('collapsed');
        minimizedBar.classList.add('visible');
    }

    function expandPanel() {
        minimizedBar.classList.remove('visible');
        expandedPanel.classList.remove('collapsed');
    }

    expandedPanel.addEventListener('click', (e) => {
        const target = e.target.closest('input, button');
        if (!(target && isInteractiveElement(target))) {
            collapsePanel();
        }
    });

    minimizedBar.addEventListener('click', expandPanel);

    // ---------- Загрузка сайта ----------
    function loadSite() {
    if (!isValidUrl(input.value)) return;
        showSplash();
        let url = input.value.trim();
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        // Используем прокси-эндпоинт
        iframe.src = `/api/yellow-mirror/?target=${encodeURIComponent(url)}`;
    }

    button.addEventListener('click', loadSite);

    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (isValidUrl(input.value)) {
                loadSite();
            }
        }
    });

    iframe.addEventListener('error', () => {
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    });
})();