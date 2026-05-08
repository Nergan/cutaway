// ... (Keep the existing UI toggles and register SW code exactly as before) ...

function simplifyUrl(url) {
    if (!url) return '';
    let simplified = url.replace(/\/$/, '');
    simplified = simplified.replace(/^https?:\/\//i, '');
    simplified = simplified.replace(/^www\./i, '');
    return simplified;
}

function loadTarget(pushHistory = true) {
    let url = UI.input.value.trim();
    if (!url) {
        UI.iframe.src = 'about:blank';
        UI.video.style.display = 'block';
        return;
    }
    if (!url.startsWith('http')) url = 'https://' + url;
    
    UI.video.style.display = 'none';
    UI.iframe.src = '/yellow-mirror/proxy/' + url;
    
    if (pushHistory) {
        const currentTarget = new URLSearchParams(window.location.search).get('target');
        if (url !== currentTarget) {
            history.pushState({ url }, '', `/yellow-mirror/?target=${encodeURIComponent(url)}`);
        }
    }
    UI.input.value = simplifyUrl(url);
}

UI.btn.addEventListener('click', () => loadTarget(true));
UI.input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') loadTarget(true);
});

// Update input when Iframe navigates
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'ym-nav') {
        UI.input.value = simplifyUrl(e.data.url);
        history.replaceState({ url: e.data.url }, '', `/yellow-mirror/?target=${encodeURIComponent(e.data.url)}`);
    }
});

// FIX: Handle the browser "Back" and "Forward" arrows correctly.
window.addEventListener('popstate', (e) => {
    const params = new URLSearchParams(window.location.search);
    const target = params.get('target');
    
    if (target) {
        UI.input.value = target;
        loadTarget(false); // Load without pushing history again
    } else {
        // If we hit back until there is no target, clear the proxy and show video
        UI.input.value = '';
        UI.iframe.src = 'about:blank';
        UI.video.style.display = 'block';
    }
});

window.addEventListener('load', () => {
    const target = new URLSearchParams(window.location.search).get('target');
    if (target) {
        UI.input.value = target;
        loadTarget(false);
    }
});