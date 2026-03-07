window.YM = window.YM || {};

YM.navigator = {
    load: function(target, options = {}) {
        if (!target) return;
        if (target.startsWith('about:') || target.startsWith('data:') || target.startsWith('javascript:')) {
            return;
        }
        const normalized = YM.normalizeUrl(target);

        if (YM.background) YM.background.hide();

        const apiUrl = `api/?target=${encodeURIComponent(normalized)}`;

        fetch(apiUrl, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }
            const finalUrl = response.url;
            let finalTarget = normalized;
            try {
                const urlObj = new URL(finalUrl, window.location.origin);
                const t = urlObj.searchParams.get('target');
                if (t) finalTarget = t;
            } catch (e) {}
            return response.text().then(html => ({ html, finalTarget }));
        })
        .then(({ html, finalTarget }) => {
            // Устанавливаем флаг, чтобы init.js не перезагружал страницу
            sessionStorage.setItem('ym_just_loaded', 'true');
            document.open();
            document.write(html);
            document.close();

            const currentTarget = YM.getTargetFromUrl();
            if (finalTarget !== currentTarget) {
                YM.history.replaceCurrent(finalTarget);
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки:', error);
            alert('Не удалось загрузить сайт: ' + error.message);
            if (YM.background) YM.background.show();
        });
    },

    navigate: function(url) {
        if (!url) return;
        let targetUrl = url;
        try {
            const linkUrl = new URL(url, window.location.href);
            if (linkUrl.pathname.includes('/api/') || linkUrl.searchParams.has('target')) {
                const t = linkUrl.searchParams.get('target');
                if (t) targetUrl = t;
            }
        } catch (e) {}

        YM.history.push(targetUrl);
    },

    submitForm: function(form) {
        const formData = new FormData(form);
        const method = form.method.toUpperCase() || 'GET';
        const action = form.action;

        let targetUrl = action;
        try {
            const urlObj = new URL(action, window.location.href);
            const t = urlObj.searchParams.get('target');
            if (t) targetUrl = t;
        } catch (e) {}

        if (method === 'GET') {
            const params = new URLSearchParams(formData).toString();
            if (params) {
                targetUrl += (targetUrl.includes('?') ? '&' : '?') + params;
            }
            YM.history.push(targetUrl);
        } else {
            const apiUrl = `api/?target=${encodeURIComponent(targetUrl)}`;
            fetch(apiUrl, {
                method: method,
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error ${response.status}`);
                const finalUrl = response.url;
                let finalTarget = targetUrl;
                try {
                    const urlObj = new URL(finalUrl, window.location.origin);
                    const t = urlObj.searchParams.get('target');
                    if (t) finalTarget = t;
                } catch (e) {}
                return response.text().then(html => ({ html, finalTarget }));
            })
            .then(({ html, finalTarget }) => {
                sessionStorage.setItem('ym_just_loaded', 'true');
                document.open();
                document.write(html);
                document.close();
                const currentTarget = YM.getTargetFromUrl();
                if (finalTarget !== currentTarget) {
                    YM.history.replaceCurrent(finalTarget);
                }
            })
            .catch(error => {
                console.error('Ошибка отправки формы:', error);
                alert('Ошибка отправки формы: ' + error.message);
            });
        }
    },

    loadSite: function() {
        const trimmed = YM.elements.input.value.trim();
        let url = trimmed;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        YM.history.push(url);
    }
};