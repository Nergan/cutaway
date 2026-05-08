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

// URL formatting for display
function simplifyUrl(url) {
    if (!url) return '';
    let simplified = url.replace(/\/$/, '');
    simplified = simplified.replace(/^https?:\/\//i, '');
    simplified = simplified.replace(/^www\./i, '');
    return simplified;
}

// UI Panel Toggles & Hover Logic (Restored)
UI.minBar.addEventListener('click', () => {
    UI.panel.classList.remove('collapsed');
    UI.minBar.classList.remove('visible');
});

UI.panel.addEventListener('click', (e) => {
    const target = e.target.closest('input, button');
    if (!(target && (target.tagName === 'INPUT' || target.tagName === 'BUTTON'))) {
        UI.panel.classList.add('collapsed');
        UI.minBar.classList.add('visible');
    }
});

UI.panel.addEventListener('mouseover', (e) => {
    const target = e.target.closest('input, button');
    UI.panel.classList.toggle('panel-highlight', !(target && (target.tagName === 'INPUT' || target.tagName === 'BUTTON')));
});

UI.panel.addEventListener('mouseout', (e) => {
    const related = e.relatedTarget;
    if (!related || !UI.panel.contains(related)) {
        UI.panel.classList.remove('panel-highlight');
    }
});

// Proxy Loading
function loadTarget() {
    let url = UI.input.value.trim();
    if (!url) return;
    if (!url.startsWith('http')) url = 'https://' + url;
    
    UI.video.style.display = 'none';
    UI.iframe.src = '/yellow-mirror/proxy/' + url;
    
    const currentTarget = new URLSearchParams(window.location.search).get('target');
    if (url !== currentTarget) {
        history.pushState({ url }, '', `/yellow-mirror/?target=${encodeURIComponent(url)}`);
    }
    UI.input.value = simplifyUrl(url);
}

UI.btn.addEventListener('click', loadTarget);
UI.input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') loadTarget();
});

// History Hook sync from iframe
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'ym-nav') {
        UI.input.value = simplifyUrl(e.data.url);
        history.replaceState({ url: e.data.url }, '', `/yellow-mirror/?target=${encodeURIComponent(e.data.url)}`);
    }
});

window.addEventListener('load', () => {
    const target = new URLSearchParams(window.location.search).get('target');
    if (target) {
        UI.input.value = target;
        loadTarget();
    }
});