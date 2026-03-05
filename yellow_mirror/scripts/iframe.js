window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,

    /**
     * Загружает целевой URL в iframe через прокси.
     * Если это startpage.com — показывает сообщение и ничего не загружает.
     */
    loadTarget: function(target) {
        if (!target) return;

        // Игнорируем служебные схемы
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            YM.splash.show();
            return;
        }

        // Если это внутренний путь приложения — редирект
        if (YM.isSelfAppUrl(target)) {
            window.location.href = target;
            return;
        }

        // Блокировка для startpage.com
        try {
            const urlObj = new URL(target);
            if (urlObj.hostname.includes('startpage.com')) {
                YM.showBlockedMessage(); // показываем сообщение, iframe не трогаем
                return;
            }
        } catch (e) {
            // Некорректный URL — дальше проверит isValidUrl
        }

        // Нормализуем URL и загружаем через прокси
        const normalizedTarget = YM.normalizeUrl(target);
        this.ignoreNextLoad = false;
        YM.splash.show();
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    /**
     * Обработчик успешной загрузки iframe.
     */
    handleLoad: function() {
        YM.splash.hide();

        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let targetUrl = currentIframeSrc;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) targetUrl = target;
            } else {
                // Если это не прокси (например, about:blank), не обновляем URL
                const urlObj = new URL(currentIframeSrc, window.location.origin);
                if (urlObj.protocol !== 'http:' && urlObj.protocol !== 'https:') {
                    return;
                }
            }

            if (YM.isSelfAppUrl(targetUrl)) {
                window.location.href = targetUrl;
                return;
            }

            setTimeout(() => {
                if (YM.iframe.ignoreNextLoad) {
                    YM.iframe.ignoreNextLoad = false;
                } else {
                    // Используем pushState, чтобы главная оставалась в истории
                    YM.pushBrowserUrl(targetUrl);
                }
            }, 0);
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
        }
    },

    /**
     * Обработчик ошибки загрузки iframe.
     */
    handleError: function() {
        YM.splash.hide();
        console.warn('Не удалось загрузить сайт в iframe (возможно, запрещено встраивание).');
    },

    /**
     * Загружает сайт из поля ввода.
     */
    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        if (!YM.isValidUrl(trimmed) || YM.isSelfUrl(trimmed)) return;

        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        YM.iframe.loadTarget(url);
    }
};

/**
 * Показывает сообщение о блокировке на 5 секунд.
 * Не изменяет содержимое iframe и не скрывает сплэш.
 */
YM.showBlockedMessage = function() {
    const msgEl = document.getElementById('error-message');
    if (!msgEl) return;
    // НЕ скрываем сплэш — оставляем фон стартовой страницы или текущий контент
    msgEl.classList.remove('hidden');
    setTimeout(() => {
        msgEl.classList.add('hidden');
    }, 5000);
};

/**
 * Слушатель сообщений от iframe (для навигации внутри прокси).
 */
window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'iframe-navigation') {
        const frameUrl = event.data.url;
        try {
            let targetUrl = frameUrl;
            if (frameUrl.includes('/api/')) {
                const urlObj = new URL(frameUrl, window.location.origin);
                const target = urlObj.searchParams.get('target');
                if (target) targetUrl = target;
            }

            if (YM.isSelfAppUrl(targetUrl)) {
                window.location.href = targetUrl;
                return;
            }

            const normalizedTarget = YM.normalizeUrl(targetUrl);

            YM.elements.input.value = YM.simplifyUrl(normalizedTarget);
            YM.panel.updateValidity();

            YM.pushBrowserUrl(normalizedTarget);

            YM.iframe.ignoreNextLoad = true;
        } catch (e) {
            console.warn('Не удалось обработать сообщение от iframe', e);
        }
    }
});