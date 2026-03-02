(function() {
    // ---------- Элементы DOM ----------
    const expandedPanel = document.getElementById('expandedPanel');
    const minimizedBar = document.getElementById('minimizedBar');
    const input = document.getElementById('url-input');
    const button = document.getElementById('load-site-btn');
    const iframe = document.getElementById('site-frame');
    const splash = document.getElementById('splash');
    const splashLayer = document.querySelector('.splash-layer');

    // Переменные для анимации движения слоя и хранения последнего загруженного URL
    let targetX = 0, targetY = 0;
    let currentX = 0, currentY = 0;
    let rafId = null;
    const maxOffset = 25; // максимальное смещение в процентах
    let lastLoadedUrl = null; // полный URL последнего успешно загруженного сайта

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
    iframe.addEventListener('load', handleIframeLoad);
    iframe.addEventListener('error', handleIframeError);

    // ---------- Обработка событий iframe ----------
    function handleIframeLoad() {
        hideSplash();
        // После успешной загрузки показываем в поле упрощённый домен
        if (lastLoadedUrl) {
            input.value = simplifyToDomain(lastLoadedUrl);
            updateValidity(); // обновляем состояние кнопки (должна остаться активной)
        }
    }

    function handleIframeError() {
        hideSplash();
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
        // При ошибке не меняем поле ввода
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

    // ---------- Проверка, ведёт ли ссылка на ТЕКУЩУЮ СТРАНИЦУ (полное совпадение URL) ----------
    function isSelfUrl(inputStr) {
        try {
            let urlString = inputStr.trim();
            if (!/^https?:\/\//i.test(urlString)) {
                urlString = 'https://' + urlString; // добавляем схему для парсинга
            }
            const inputUrl = new URL(urlString);
            const currentUrl = new URL(window.location.href);

            // Сравниваем host (хост:порт, регистронезависимо) и путь + query + hash
            const sameHost = inputUrl.host.toLowerCase() === currentUrl.host.toLowerCase();
            const samePath = inputUrl.pathname === currentUrl.pathname;
            const sameSearch = inputUrl.search === currentUrl.search;
            const sameHash = inputUrl.hash === currentUrl.hash;

            return sameHost && samePath && sameSearch && sameHash;
        } catch {
            return false; // при ошибке парсинга считаем, что не сам
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

    // ---------- Загрузка сайта через прокси ----------
    function loadSite() {
        const trimmed = input.value.trim();
        if (!isValidUrl(trimmed) || isSelfUrl(trimmed)) return;

        showSplash();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        // Сохраняем полный URL для последующего форматирования поля
        lastLoadedUrl = url;
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

    // ---------- Упрощение URL до домена ----------
    /**
     * Извлекает домен из сырой строки URL (удаляет протокол, путь, параметры и www)
     * @param {string} raw - строка, которую вставил пользователь
     * @returns {string} упрощённый домен или исходная строка, если парсинг не удался
     */
    function simplifyToDomain(raw) {
        const trimmed = raw.trim();
        if (!trimmed) return raw;

        // Добавляем схему, если её нет, для корректного парсинга
        let urlString = trimmed;
        if (!/^https?:\/\//i.test(urlString)) {
            urlString = 'https://' + urlString;
        }

        try {
            const url = new URL(urlString);
            let hostname = url.hostname;
            // Убираем www. (регистронезависимо)
            hostname = hostname.replace(/^www\./i, '');
            return hostname;
        } catch {
            // Если не удалось распарсить, оставляем как есть
            return raw;
        }
    }
})();