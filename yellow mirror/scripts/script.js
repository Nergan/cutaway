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
        let simplified = url.replace(/^https?:\/\//i, '');
        simplified = simplified.replace(/^www\./i, '');
        return simplified;
    }

    // ---------- Получение текущего target из адресной строки ----------
    function getTargetFromUrl() {
        return new URL(window.location.href).searchParams.get('target');
    }

    // ---------- Обновление адресной строки (query-параметр target) ----------
    function setBrowserUrlTarget(target) {
        const url = new URL(window.location.href);
        if (target) {
            url.searchParams.set('target', target);
        } else {
            url.searchParams.delete('target');
        }
        window.history.pushState({}, '', url);
    }

    // ---------- Загрузка целевого сайта в iframe ----------
    function loadTarget(target) {
        if (!target) return;
        showSplash();
        iframe.src = `/api/yellow-mirror/?target=${encodeURIComponent(target)}`;
    }

    // ---------- Обработка загрузки iframe ----------
    function handleIframeLoad() {
        hideSplash();

        try {
            const currentIframeSrc = iframe.src;

            // Определяем реальный целевой URL
            let targetUrl = currentIframeSrc;
            if (currentIframeSrc.includes('/api/yellow-mirror/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) targetUrl = target;
            }

            // Обновляем поле ввода
            input.value = simplifyUrl(targetUrl);
            updateValidity();

            // Синхронизируем адресную строку
            const currentTarget = getTargetFromUrl();
            if (currentTarget !== targetUrl) {
                setBrowserUrlTarget(targetUrl);
            }
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
        }
    }

    function handleIframeError() {
        hideSplash();
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    }

    iframe.addEventListener('load', handleIframeLoad);
    iframe.addEventListener('error', handleIframeError);

    // ---------- Загрузка сайта через прокси (по вводу пользователя) ----------
    function loadSite() {
        const trimmed = input.value.trim();
        if (!isValidUrl(trimmed) || isSelfUrl(trimmed)) return;

        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        loadTarget(url);
    }

    button.addEventListener('click', loadSite);

    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            loadSite();
        }
    });

    // ---------- Обработка навигации браузера (вперёд/назад) ----------
    window.addEventListener('popstate', () => {
        const target = getTargetFromUrl();
        if (target) {
            loadTarget(target);
        } else {
            // Если параметра нет, показываем заглушку
            iframe.src = 'about:blank';
            showSplash();
            input.value = '';
            updateValidity();
        }
    });

    // ---------- Инициализация при загрузке страницы ----------
    showSplash(); // показываем заглушку по умолчанию

    const initialTarget = getTargetFromUrl();
    if (initialTarget) {
        loadTarget(initialTarget);
    }
})();