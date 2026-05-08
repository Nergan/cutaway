// Register SW with Root Scope. This works because we return Service-Worker-Allowed: / in FastAPI
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/yellow-mirror/sw.js', { scope: '/' })
        .then(reg => console.log('Yellow Mirror SW Active!'))
        .catch(err => console.error('SW Failed:', err));
}

const UI = {
    input: document.getElementById('url-input'),
    iframe: document.getElementById('site-frame'),
    btn: document.getElementById('load-site-btn'),
    video: document.getElementById('background-video'),
    panel: document.getElementById('expandedPanel'),
    minBar: document.getElementById('minimizedBar')
};

UI.minBar.addEventListener('click', () => {
    UI.panel.classList.remove('collapsed');
    UI.minBar.classList.remove('visible');
});

UI.panel.addEventListener('click', (e) => {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'BUTTON') {
        UI.panel.classList.add('collapsed');
        UI.minBar.classList.add('visible');
    }
});

function loadTarget() {
    let url = UI.input.value.trim();
    if (!url) return;
    if (!url.startsWith('http')) url = 'https://' + url;
    
    UI.video.style.display = 'none';
    UI.iframe.src = '/yellow-mirror/proxy/' + url;
    history.pushState({ url }, '', `/yellow-mirror/?target=${encodeURIComponent(url)}`);
}

UI.btn.addEventListener('click', loadTarget);
UI.input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') loadTarget();
});

// Update the address bar perfectly synchronized with the Iframe
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'ym-nav') {
        UI.input.value = e.data.url;
        history.replaceState({ url: e.data.url }, '', `/yellow-mirror/?target=${encodeURIComponent(e.data.url)}`);
    }
});

// Handle initial target from URL parameters
window.addEventListener('load', () => {
    const params = new URLSearchParams(window.location.search);
    const target = params.get('target');
    if (target) {
        UI.input.value = target;
        loadTarget();
    }
});