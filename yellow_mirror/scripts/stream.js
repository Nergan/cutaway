window.YM = window.YM || {};

YM.stream = {
    sessionId: null,
    streamActive: false,

    async loadSite(url) {
        if (!url) return;
        if (!url.match(/^https?:\/\//i)) {
            url = 'https://' + url;
        }
        const normalized = YM.normalizeUrl(url);
        YM.elements.input.value = YM.simplifyUrl(normalized);
        YM.panel.updateValidity();

        try {
            const response = await fetch('/api/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: normalized})
            });
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Server error:', errorText);
                alert('Ошибка запуска браузера на сервере. Проверьте консоль.');
                return;
            }
            const data = await response.json();
            this.sessionId = data.session_id;
            this.startStream();
        } catch (e) {
            console.error('Failed to start browser:', e);
            alert('Не удалось связаться с сервером.');
        }
    },

    startStream() {
        if (!this.sessionId) return;
        YM.elements.streamContainer.style.display = 'block';
        YM.elements.clickOverlay.style.display = 'block';
        YM.background.hide();

        YM.elements.streamImage.src = `/api/stream/${this.sessionId}`;
        this.streamActive = true;
    },

    stopStream() {
        YM.elements.streamContainer.style.display = 'none';
        YM.elements.clickOverlay.style.display = 'none';
        YM.elements.streamImage.src = '';
        this.streamActive = false;
        this.sessionId = null;
        YM.background.show();
    },

    handleClick(e) {
        if (!this.streamActive || !this.sessionId) return;
        const rect = YM.elements.streamImage.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const scaleX = YM.elements.streamImage.naturalWidth / rect.width;
        const scaleY = YM.elements.streamImage.naturalHeight / rect.height;
        const scaledX = Math.round(x * scaleX);
        const scaledY = Math.round(y * scaleY);

        fetch(`/api/click/${this.sessionId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({x: scaledX, y: scaledY})
        }).catch(e => console.warn('Click failed', e));
    },

    handleKey(e) {
        if (!this.streamActive || !this.sessionId) return;
        const key = e.key;
        if (key === 'Shift' || key === 'Control' || key === 'Alt' || key === 'Meta') return;

        if (key.length === 1) {
            fetch(`/api/key/${this.sessionId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: key})
            }).catch(e => console.warn('Key send failed', e));
        } else {
            fetch(`/api/key/${this.sessionId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key: key})
            }).catch(e => console.warn('Key send failed', e));
        }
    }
};

YM.elements.clickOverlay.addEventListener('click', (e) => YM.stream.handleClick(e));
YM.elements.clickOverlay.addEventListener('keydown', (e) => YM.stream.handleKey(e));
YM.elements.clickOverlay.setAttribute('tabindex', '0');