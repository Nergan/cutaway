window.YM = window.YM || {};

YM.iframe = {
    ignoreNextLoad: false,
    errorTimeout: null, // для автоматического скрытия тоста

    // Показать сообщение об ошибке
    showError: function(message) {
        const toast = document.getElementById('error-toast');
        if (!toast) return;
        toast.textContent = message || 'Sorry, it is impossible to access the site';
        toast.classList.remove('hidden');
        toast.classList.add('visible');
        if (this.errorTimeout) clearTimeout(this.errorTimeout);
        this.errorTimeout = setTimeout(() => {
            toast.classList.remove('visible');
            toast.classList.add('hidden');
        }, 5000);
    },

    // Скрыть сообщение об ошибке
    hideError: function() {
        const toast = document.getElementById('error-toast');
        if (!toast) return;
        toast.classList.remove('visible');
        toast.classList.add('hidden');
        if (this.errorTimeout) clearTimeout(this.errorTimeout);
    },

    loadTarget: function(target) {
        if (!target) return;

        // Скрываем предыдущее сообщение об ошибке
        this.hideError();

        if (YM.isSelfAppUrl(target)) {
            window.location.href = target;
            return;
        }

        const normalizedTarget = YM.normalizeUrl(target);
        this.ignoreNextLoad = false;
        YM.splash.show();
        YM.elements.iframe.src = `api/?target=${encodeURIComponent(normalizedTarget)}`;
    },

    handleLoad: function() {
        YM.splash.hide();
        YM.iframe.hideError(); // скрываем тост, если он был виден

        // Проверяем, не загрузилась ли наша главная страница (из-за редиректа)
        try {
            const iframeWindow = YM.elements.iframe.contentWindow;
            if (iframeWindow && iframeWindow.YM_HOME_PAGE) {
                YM.iframe.showError('Sorry, it is impossible to access the site');
                return; // Не обновляем URL, не меняем адресную строку
            }
        } catch (e) {
            // Игнорируем ошибки доступа к contentWindow
        }

        try {
            const currentIframeSrc = YM.elements.iframe.src;
            let targetUrl = currentIframeSrc;

            if (currentIframeSrc.includes('/api/')) {
                const urlParams = new URL(currentIframeSrc).searchParams;
                const target = urlParams.get('target');
                if (target) targetUrl = target;
            }

            if (YM.isSelfAppUrl(targetUrl)) {
                window.location.href = targetUrl;
                return;
            }

            setTimeout(() => {
                if (YM.iframe.ignoreNextLoad) {
                    YM.iframe.ignoreNextLoad = false;
                } else {
                    YM.replaceBrowserUrl(targetUrl);
                }
            }, 0);
        } catch (e) {
            console.warn('Не удалось обработать загрузку iframe', e);
        }
    },

    handleError: function() {
        YM.splash.hide();
        YM.iframe.hideError();
        YM.iframe.showError('Sorry, it is impossible to access the site');
        // Не меняем URL, не редиректим
    },

    loadSite: function() { ... } // без изменений
};

// Обработчик сообщений от iframe
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

            // Если внутренняя навигация привела на главную страницу приложения — показываем ошибку
            if (YM.isSelfAppUrl(targetUrl)) {
                YM.iframe.showError('Sorry, it is impossible to access the site');
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