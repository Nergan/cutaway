(function() {
    // ---------- Элементы DOM ----------
    const expandedPanel = document.getElementById('expandedPanel');
    const minimizedBar = document.getElementById('minimizedBar');
    const input = document.getElementById('url-input');
    const button = document.getElementById('load-site-btn');
    const iframe = document.getElementById('site-frame');
    const splash = document.getElementById('splash');
    const splashLayer = document.querySelector('.splash-layer');

    // Путь к собственному приложению
    const SELF_APP_PATH = '/yellow-mirror';

    // Переменные для анимации движения слоя
    let targetX = 0, targetY = 0;
    let currentX = 0, currentY = 0;
    let rafId = null;
    const maxOffset = 25;

    // Флаг для предотвращения двойной обработки загрузки iframe
    let ignoreNextLoad = false;

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

    // ---------- Валидация URL (без изменений) ----------
    function isValidIPv4(str) { /* ... */ }
    function isValidIPv6(str) { /* ... */ }
    function isIP(str) { /* ... */ }
    function isValidDomain(host) { /* ... */ }
    function normalizeInput(str) { /* ... */ }
    function isValidUrl(str) { /* ... */ }
    function isSelfUrl(inputStr) { /* ... */ }

    // ---------- Обновление состояния валидности и кнопки ----------
    function updateValidity() {
        const trimmed = input.value.trim();
        const valid = isValidUrl(trimmed) && !isSelfUrl(trimmed);
        button.disabled = !valid;
        input.classList.toggle('invalid', !valid);
    }

    input.addEventListener('input', updateValidity);

    // ---------- Подсветка панели (без изменений) ----------
    function isInteractiveElement(el) { /* ... */ }
    function setPanelHighlight(enable) { /* ... */ }
    expandedPanel.addEventListener('mouseover', (e) => { /* ... */ });
    expandedPanel.addEventListener('mouseout', (e) => { /* ... */ });

    // ---------- Сворачивание / разворачивание (без изменений) ----------
    function collapsePanel() { /* ... */ }
    function expandPanel() { /* ... */ }
    expandedPanel.addEventListener('click', (e) => { /* ... */ });
    minimizedBar.addEventListener('click', expandPanel);

    // ---------- Функции для работы с URL ----------
    function normalizeUrl(url) {
        if (!url) return url;
        return url.replace(/\/$/, '');
    }

    function simplifyUrl(url) {
        if (!url) return '';
        const normalized = normalizeUrl(url);
        let simplified = normalized.replace(/^https?:\/\//i, '');
        simplified = simplified.replace(/^www\./i, '');
        return simplified;
    }

    function getTargetFromUrl() {
        return new URL(window.location.href).searchParams.get('target');
    }

    function replaceBrowserUrl(target) {
        const url = new URL(window.location.href);
        const currentTarget = url.searchParams.get('target');
        const normalizedTarget = target ? normalizeUrl(target) : target;
        if (normalizedTarget === currentTarget) return;
        if (normalizedTarget) {
            url.searchParams.set('target', normalizedTarget);
        } else {
            url.searchParams.delete('target');
        }
        window.history.replaceState({}, '', url);
    }

    function pushBrowserUrl(target) {
        const url = new URL(window.location.href);
        const currentTarget = url.searchParams.get('target');
        const normalizedTarget = target ? normalizeUrl(target) : target;
        if (normalizedTarget === currentTarget) return;
        if (normalizedTarget) {
            url.searchParams.set('target', normalizedTarget);
        } else {
            url.searchParams.delete('target');
        }
        window.history.pushState({}, '', url);
    }

    /**
     * Проверяет, является ли URL ссылкой на собственное приложение (yellow-mirror)
     */
    function isSelfAppUrl(urlString) {
        try {
            const url = new URL(urlString, window.location.origin);
            return url.pathname === SELF_APP_PATH || url.pathname === SELF_APP_PATH + '/';
        } catch {
            return false;
        }
    }

    function loadTarget(target) {
        if (!target) return;

        // Если целевой URL ведёт на наше приложение, выполняем редирект на него (выходим из iframe)
        if (isSelfAppUrl(target)) {
            window.location.href = target;  // или можно использовать "/yellow-mirror"
            return;
        }

        const normalizedTarget = normalizeUrl(target);
        ignoreNextLoad = false;
        showSplash();
        iframe.src = `/api/yellow-mirror/?target=${encodeURIComponent(normalizedTarget)}`;
    }

    function handleIframeLoad() {
        hideSplash();

        try {
            const currentIframeSrc = iframe.src;
            let targetUrl = currentIframeSrc;

            if (currentIframeSrc.includes('/api/yellow-mirror/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) targetUrl = target;
            }

            // Если загруженный URL ведёт на наше приложение, редиректим родителя
            if (isSelfAppUrl(targetUrl)) {
                window.location.href = targetUrl;
                return;
            }

            setTimeout(() => {
                if (ignoreNextLoad) {
                    ignoreNextLoad = false;
                } else {
                    replaceBrowserUrl(targetUrl);
                }
            }, 0);
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

    window.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'iframe-navigation') {
            const frameUrl = event.data.url;
            try {
                let targetUrl = frameUrl;
                if (frameUrl.includes('/api/yellow-mirror/')) {
                    const urlObj = new URL(frameUrl, window.location.origin);
                    const target = urlObj.searchParams.get('target');
                    if (target) targetUrl = target;
                }

                // Если новый URL ведёт на наше приложение, редиректим родителя
                if (isSelfAppUrl(targetUrl)) {
                    window.location.href = targetUrl;
                    return;
                }

                const normalizedTarget = normalizeUrl(targetUrl);

                input.value = simplifyUrl(normalizedTarget);
                updateValidity();

                pushBrowserUrl(normalizedTarget);

                ignoreNextLoad = true;
            } catch (e) {
                console.warn('Не удалось обработать сообщение от iframe', e);
            }
        }
    });

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

    window.addEventListener('popstate', () => {
        const target = getTargetFromUrl();
        if (target) {
            loadTarget(target);
        } else {
            iframe.src = 'about:blank';
            showSplash();
            input.value = '';
            updateValidity();
        }
    });

    // Инициализация: если в URL есть target, ведущий на наше приложение, редиректим
    const initialTarget = getTargetFromUrl();
    if (initialTarget) {
        if (isSelfAppUrl(initialTarget)) {
            // Если target указывает на наше приложение, сразу переходим на него (без параметра)
            window.location.href = '/yellow-mirror';  // или initialTarget, но уберём target
        } else {
            const normalized = normalizeUrl(initialTarget);
            input.value = simplifyUrl(normalized);
            updateValidity();
            loadTarget(normalized);
        }
    }
})();