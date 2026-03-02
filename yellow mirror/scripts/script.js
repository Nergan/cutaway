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
    const maxOffset = 25;

    // ---------- Управление заглушкой и iframe ----------
    function showSplash() {
        splash.style.display = 'block';
        iframe.style.pointerEvents = 'none';
        startMouseTracking();
    }

    function hideSplash() {
        splash.style.display = 'none';
        iframe.style.pointerEvents = 'auto';
        stopMouseTracking();
    }

    // ---------- Отслеживание мыши для движения слоя ----------
    function handleMouseMove(e) {
        if (!splashLayer || splash.style.display === 'none') return;
        const x = (e.clientX / window.innerWidth) * 2 - 1;
        const y = (e.clientY / window.innerHeight) * 2 - 1;
        targetX = -x * maxOffset;
        targetY = -y * maxOffset;
    }

    function updateLayerTransform() {
        if (!splashLayer || splash.style.display === 'none') return;
        currentX += (targetX - currentX) * 0.1;
        currentY += (targetY - currentY) * 0.1;
        splashLayer.style.transform = `translate(${currentX}%, ${currentY}%)`;
        rafId = requestAnimationFrame(updateLayerTransform);
    }

    function startMouseTracking() {
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
        if (splashLayer) {
            splashLayer.style.transform = 'translate(0%, 0%)';
        }
        currentX = 0; currentY = 0; targetX = 0; targetY = 0;
    }

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

    // ---------- Проверка, ведёт ли ссылка на ТЕКУЩУЮ СТРАНИЦУ ----------
    function isSelfUrl(inputStr) {
        try {
            let urlString = inputStr.trim();
            if (!/^https?:\/\//i.test(urlString)) {
                urlString = 'https://' + urlString;
            }
            const inputUrl = new URL(urlString);
            const currentUrl = new URL(window.location.href);

            const sameHost = inputUrl.host.toLowerCase() === currentUrl.host.toLowerCase();
            const samePath = inputUrl.pathname === currentUrl.pathname;
            const sameSearch = inputUrl.search === currentUrl.search;
            const sameHash = inputUrl.hash === currentUrl.hash;

            return sameHost && samePath && sameSearch && sameHash;
        } catch {
            return false;
        }
    }

    // ---------- Обновление состояния валидности и кнопки ----------
    function updateValidity() {
        const trimmed = input.value.trim();
        const validFormat = isValidUrl(trimmed);
        const self = isSelfUrl(trimmed);
        const valid = validFormat && !self;
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

    // ---------- Упрощение URL (удаление протокола и www) ----------
    function simplifyUrl(url) {
        // Удаляем протокол http:// или https://
        let simplified = url.replace(/^https?:\/\//i, '');
        // Удаляем www. в начале
        simplified = simplified.replace(/^www\./i, '');
        return simplified;
    }

    // ---------- Обновление адресной строки (query-параметр target) ----------
    function updateBrowserUrl(targetUrl) {
        const url = new URL(window.location.href);
        url.searchParams.set('target', targetUrl);
        window.history.pushState({}, '', url);
    }

    // ---------- Обработка загрузки iframe ----------
    function handleIframeLoad() {
        hideSplash();

        // Получаем целевой URL из src iframe (параметр target)
        try {
            const iframeSrc = iframe.src;
            const urlParams = new URL(iframeSrc).searchParams;
            const target = urlParams.get('target');
            if (target) {
                // Обновляем поле ввода
                input.value = simplifyUrl(target);
                updateValidity();
                // Обновляем адресную строку
                updateBrowserUrl(target);
            }
        } catch (e) {
            console.warn('Не удалось обработать src iframe', e);
        }
    }

    function handleIframeError() {
        hideSplash();
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    }

    iframe.addEventListener('load', handleIframeLoad);
    iframe.addEventListener('error', handleIframeError);

    // ---------- Инициализация из URL (если есть параметр target) ----------
    function initFromUrl() {
        const urlParams = new URL(window.location.href).searchParams;
        const target = urlParams.get('target');
        if (target) {
            showSplash();
            iframe.src = `/api/yellow-mirror/?target=${encodeURIComponent(target)}`;
            // Поле ввода обновится после загрузки в handleIframeLoad
        } else {
            // Если параметра нет, просто показываем заглушку (она уже видна)
        }
    }

    // ---------- Загрузка сайта через прокси ----------
    function loadSite() {
        const trimmed = input.value.trim();
        if (!isValidUrl(trimmed) || isSelfUrl(trimmed)) return;

        showSplash();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        iframe.src = `/api/yellow-mirror/?target=${encodeURIComponent(url)}`;
    }

    button.addEventListener('click', loadSite);

    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const trimmed = input.value.trim();
            if (isValidUrl(trimmed) && !isSelfUrl(trimmed)) {
                loadSite();
            }
        }
    });

    // Запускаем инициализацию после того, как все обработчики установлены
    showSplash(); // показываем заглушку при старте
    initFromUrl();
})();