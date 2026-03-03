(function() {
    // ---------- Элементы DOM ----------
    const expandedPanel = document.getElementById('expandedPanel');
    const minimizedBar = document.getElementById('minimizedBar');
    const input = document.getElementById('url-input');
    const button = document.getElementById('load-site-btn');
    const iframe = document.getElementById('site-frame');
    const splash = document.getElementById('splash');
    const splashLayer = document.querySelector('.splash-layer');

    // Путь к собственному приложению (без завершающего слеша)
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
    function isValidIPv4(str) {
        let s = str;
        if (s.endsWith('.')) {
            s = s.slice(0, -1);
        }
        const parts = s.split('.');
        if (parts.length !== 4) return false;
        return parts.every(part => {
            if (!/^\d+$/.test(part)) return false;
            const num = parseInt(part, 10);
            return num >= 0 && num <= 255;
        });
    }

    function isValidIPv6(str) {
        let address = str.replace(/^\[|\]$/g, '');
        const ipv6Regex = /^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::([0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}$|^([0-9a-fA-F]{1,4}:){1,6}:$|^([0-9a-fA-F]{1,4}:){1,5}:[0-9a-fA-F]{1,4}$|^([0-9a-fA-F]{1,4}:){1,4}:[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4})?$|^([0-9a-fA-F]{1,4}:){1,3}:[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,2}$|^([0-9a-fA-F]{1,4}:){1,2}:[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,3}$|^[0-9a-fA-F]{1,4}::[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,4}$|^::[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,5}$|^[0-9a-fA-F]{1,4}$/;
        return ipv6Regex.test(address);
    }

    function isIP(str) {
        return isValidIPv4(str) || isValidIPv6(str);
    }

    function isValidDomain(host) {
        if (host === "localhost") return true;
        if (host.startsWith('.') || host.endsWith('.') || host.includes('..')) return false;
        const labels = host.split('.');
        if (labels.length < 2) return false;
        for (let i = 0; i < labels.length - 1; i++) {
            const label = labels[i];
            if (label.length === 0) return false;
            if (label.startsWith('-') || label.endsWith('-')) return false;
            if (!/^[a-zA-Z0-9-]+$/.test(label)) return false;
        }
        const tld = labels[labels.length - 1];
        return tld.length >= 2 && /^[a-zA-Z]+$/.test(tld);
    }

    function normalizeInput(str) {
        const slashIndex = str.indexOf('/');
        if (slashIndex !== -1 && slashIndex > 0 && str[slashIndex - 1] === '.') {
            return str.slice(0, slashIndex - 1) + str.slice(slashIndex);
        }
        if (str.endsWith('.')) {
            return str.slice(0, -1);
        }
        return str;
    }

    function isValidUrl(str) {
        const trimmed = str.trim();
        if (trimmed === '' || /\s/.test(trimmed)) return false;
        if (isIP(trimmed)) return true;
        const normalized = normalizeInput(trimmed);
        let url;
        try {
            const urlString = /^https?:\/\//i.test(normalized) ? normalized : 'https://' + normalized;
            url = new URL(urlString);
        } catch {
            return false;
        }
        const host = url.hostname;
        if (isIP(host)) return true;
        return isValidDomain(host);
    }

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
        const valid = isValidUrl(trimmed) && !isSelfUrl(trimmed);
        button.disabled = !valid;
        input.classList.toggle('invalid', !valid);
    }

    input.addEventListener('input', updateValidity);

    // ---------- Подсветка панели (без изменений) ----------
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

    // ---------- Сворачивание / разворачивание (без изменений) ----------
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
     * Сравнивает только pathname (без query и hash) и учитывает возможный завершающий слеш.
     */
    function isSelfAppUrl(urlString) {
        try {
            const url = new URL(urlString, window.location.origin);
            // Нормализуем pathname (убираем завершающий слеш)
            const path = url.pathname.replace(/\/+$/, '');
            return path === SELF_APP_PATH;
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