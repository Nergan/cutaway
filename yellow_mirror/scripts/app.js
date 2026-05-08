// 1. Register the Service Worker
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/yellow-mirror/sw.js', { scope: '/' })
        .then(reg => console.log('Yellow Mirror SW Active!'))
        .catch(err => console.error('SW Failed:', err));
}

// 2. Define the UI object
const UI = {
    input: document.getElementById('url-input'),
    iframe: document.getElementById('site-frame'),
    btn: document.getElementById('load-site-btn'),
    video: document.getElementById('background-video'),
    panel: document.getElementById('expandedPanel'),
    minBar: document.getElementById('minimizedBar')
};

// 3. UI Panel Toggles & Hover Logic
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

// 4. URL formatting for display
function simplifyUrl(url) {
    if (!url) return '';
    let simplified = url.replace(/\/$/, '');
    simplified = simplified.replace(/^https?:\/\//i, '');
    simplified = simplified.replace(/^www\./i, '');
    return simplified;
}

// 5. Proxy Loading Logic
function loadTarget(pushHistory = true) {
    let url = UI.input.value.trim();
    
    // If the input is empty, return to the "home" state
    if (!url) {
        UI.iframe.src = 'about:blank';
        UI.video.style.display = 'block';
        return;
    }
    
    if (!url.startsWith('http')) url = 'https://' + url;
    
    // Hide video and load the proxy frame
    UI.video.style.display = 'none';
    UI.iframe.src = '/yellow-mirror/proxy/' + url;
    
    // Manage history state
    if (pushHistory) {
        const currentTarget = new URLSearchParams(window.location.search).get('target');
        if (url !== currentTarget) {
            history.pushState({ url }, '', `/yellow-mirror/?target=${encodeURIComponent(url)}`);
        }
    }
    
    UI.input.value = simplifyUrl(url);
}

// 6. Event Listeners for the GO button and Enter key
UI.btn.addEventListener('click', () => loadTarget(true));
UI.input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') loadTarget(true);
});

// 7. Receive navigation messages from the injected hook inside the iframe
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'ym-nav') {
        UI.input.value = simplifyUrl(e.data.url);
        history.replaceState({ url: e.data.url }, '', `/yellow-mirror/?target=${encodeURIComponent(e.data.url)}`);
    }
});

// 8. Handle the browser's "Back" and "Forward" arrows correctly
window.addEventListener('popstate', (e) => {
    const params = new URLSearchParams(window.location.search);
    const target = params.get('target');
    
    if (target) {
        UI.input.value = target;
        loadTarget(false); // Load without pushing to history again
    } else {
        // If we hit back until there is no target, clear the proxy and show video
        UI.input.value = '';
        UI.iframe.src = 'about:blank';
        UI.video.style.display = 'block';
    }
});

// 9. Handle initial page load with parameters (e.g., sharing a proxy link)
window.addEventListener('load', () => {
    const target = new URLSearchParams(window.location.search).get('target');
    if (target) {
        UI.input.value = target;
        loadTarget(false);
    }
});