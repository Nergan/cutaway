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

    // Переменная для отслеживания последнего src iframe (для polling)
    let lastIframeSrc = iframe.src;

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

    showSplash();
    iframe.addEventListener('load', hideSplash);
    iframe.addEventListener('error', hideSplash);

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

    // ---------- Проверка на самоссылку (текущая страница) ----------
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

    // ---------- Преобразование полного URL в укороченный вид (без протокола и www) ----------
    function shortenUrl(fullUrl) {
        try {
            const url = new URL(fullUrl);
            let host = url.hostname;
            if (host.startsWith('www.')) {
                host = host.slice(4);
            }
            // Возвращаем host + путь + поиск + хеш (путь всегда начинается с /)
            return host + url.pathname + url.search + url.hash;
        } catch {
            return fullUrl;
        }
    }

    // ---------- Извлечение целевого URL из прокси-ссылки iframe ----------
    function extractTargetFromProxySrc(proxySrc) {
        try {
            // Если src пустой или about:blank, возвращаем null
            if (!proxySrc || proxySrc === 'about:blank') return null;

            // Создаём URL относительно текущего origin (на случай, если src абсолютный)
            const url = new URL(proxySrc, window.location.origin);
            const target = url.searchParams.get('target');
            return target ? decodeURIComponent(target) : null;
        } catch (e) {
            console.warn('Не удалось распарсить src iframe:', e);
            return null;
        }
    }

    // ---------- Обновление поля ввода из текущего iframe ----------
    function updateInputFromIframe() {
        const proxySrc = iframe.src;
        if (!proxySrc || proxySrc === 'about:blank') return;

        const targetUrl = extractTargetFromProxySrc(proxySrc);
        if (targetUrl) {
            const short = shortenUrl(targetUrl);
            input.value = short;
            updateValidity();
        }
    }

    // Слушаем загрузку iframe (срабатывает при навигации)
    iframe.addEventListener('load', updateInputFromIframe);

    // ---------- Polling для отслеживания изменения src (для случаев, когда load не срабатывает) ----------
    setInterval(() => {
        if (iframe.src !== lastIframeSrc) {
            lastIframeSrc = iframe.src;
            updateInputFromIframe();
        }
    }, 300);

    // ---------- Обновление состояния кнопки ----------
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

    iframe.addEventListener('error', () => {
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    });
})();