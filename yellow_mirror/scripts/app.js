// Clean up old caching if it exists
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(registrations => {
        for (let r of registrations) {
            r.unregister();
        }
    });
}

const UI = {
    input: document.getElementById('url-input'),
    videoNative: document.getElementById('background-video'),
    imgRemote: document.getElementById('site-stream'),
    btn: document.getElementById('load-site-btn'),
    panel: document.getElementById('expandedPanel'),
    minBar: document.getElementById('minimizedBar')
};

UI.minBar.addEventListener('click', () => { UI.panel.classList.remove('collapsed'); UI.minBar.classList.remove('visible'); });
UI.panel.addEventListener('click', (e) => {
    const t = e.target.closest('input, button');
    if (!(t && (t.tagName === 'INPUT' || t.tagName === 'BUTTON'))) {
        UI.panel.classList.add('collapsed'); UI.minBar.classList.add('visible');
    }
});
UI.panel.addEventListener('mouseover', (e) => {
    const t = e.target.closest('input, button');
    UI.panel.classList.toggle('panel-highlight', !(t && (t.tagName === 'INPUT' || t.tagName === 'BUTTON')));
});
UI.panel.addEventListener('mouseout', (e) => {
    const rel = e.relatedTarget;
    if (!rel || !UI.panel.contains(rel)) UI.panel.classList.remove('panel-highlight');
});

let ws = null;
let clientId = crypto.randomUUID();

function simplifyUrl(url) {
    if (!url) return '';
    return url.replace(/\/$/, '').replace(/^https?:\/\//i, '').replace(/^www\./i, '');
}

function stopStream() {
    if (ws) { ws.close(); ws = null; }
    UI.imgRemote.style.display = 'none';
    UI.videoNative.style.display = 'block';
    UI.imgRemote.src = '';
}

async function connectStream(url) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/yellow-mirror/ws/${clientId}`);

    ws.onopen = () => {
        ws.send(JSON.stringify({ 
            type: 'init', url: url, 
            width: window.innerWidth, height: window.innerHeight 
        }));
    };

    ws.onmessage = (event) => {
        // If it's a raw string not starting with '{', it's our base64 JPEG from CDP
        if (typeof event.data === "string" && !event.data.startsWith("{")) {
            UI.imgRemote.src = "data:image/jpeg;base64," + event.data;
            UI.videoNative.style.display = 'none';
            UI.imgRemote.style.display = 'block';
        } else {
            const msg = JSON.parse(event.data);
            if (msg.type === 'navigated') {
                UI.input.value = simplifyUrl(msg.url);
                // Force correct directory structure for history pushes
                history.replaceState({ url: msg.url }, '', `/yellow-mirror/?target=${encodeURIComponent(msg.url)}`);
            }
            else if (msg.type === 'error') {
                alert(msg.message);
                stopStream();
            }
        }
    };
}

function loadTarget(pushHistory = true) {
    let url = UI.input.value.trim();
    if (!url) { stopStream(); return; }
    if (!url.startsWith('http')) url = 'https://' + url;

    if (pushHistory) {
        const cur = new URLSearchParams(window.location.search).get('target');
        if (url !== cur) history.pushState({ url }, '', `/yellow-mirror/?target=${encodeURIComponent(url)}`);
    }
    UI.input.value = simplifyUrl(url);

    if (!ws || ws.readyState !== WebSocket.OPEN) connectStream(url);
    else ws.send(JSON.stringify({ type: 'navigate', url: url }));
}

UI.btn.addEventListener('click', () => loadTarget(true));
UI.input.addEventListener('keypress', (e) => { if (e.key === 'Enter') loadTarget(true); });

function sendInput(action, payload) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', action, ...payload }));
}

const img = UI.imgRemote;
img.addEventListener('contextmenu', e => e.preventDefault());
img.addEventListener('dragstart', e => e.preventDefault());

img.addEventListener('mousemove', e => {
    const rect = img.getBoundingClientRect();
    const x = Math.round((e.clientX - rect.left) / rect.width * window.innerWidth);
    const y = Math.round((e.clientY - rect.top) / rect.height * window.innerHeight);
    sendInput('mousemove', { x, y });
});

const btnMap = { 0: 'left', 1: 'middle', 2: 'right' };
img.addEventListener('mousedown', e => { 
    // Fix: Immediately blur the input field so keys interact with the stream
    if (document.activeElement === UI.input) UI.input.blur(); 
    sendInput('mousedown', { button: btnMap[e.button] || 'left' }); 
    e.preventDefault(); 
});
img.addEventListener('mouseup', e => { sendInput('mouseup', { button: btnMap[e.button] || 'left' }); e.preventDefault(); });
img.addEventListener('wheel', e => { sendInput('wheel', { deltaX: e.deltaX, deltaY: e.deltaY }); e.preventDefault(); }, { passive: false });

window.addEventListener('keydown', e => {
    if (document.activeElement === UI.input) return;
    const key = e.key === ' ' ? 'Space' : e.key;
    sendInput('keydown', { key, code: e.code, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, shiftKey: e.shiftKey });
    if (!e.ctrlKey && !e.metaKey && e.key !== 'F12') e.preventDefault();
}, { passive: false });

window.addEventListener('keyup', e => {
    if (document.activeElement === UI.input) return;
    const key = e.key === ' ' ? 'Space' : e.key;
    sendInput('keyup', { key, code: e.code, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, shiftKey: e.shiftKey });
    e.preventDefault();
}, { passive: false });

window.addEventListener('resize', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', width: window.innerWidth, height: window.innerHeight }));
    }
});

window.addEventListener('popstate', (e) => {
    const target = new URLSearchParams(window.location.search).get('target');
    if (target) { UI.input.value = target; loadTarget(false); } 
    else { UI.input.value = ''; stopStream(); }
});

window.addEventListener('load', () => {
    const target = new URLSearchParams(window.location.search).get('target');
    if (target) { UI.input.value = target; loadTarget(false); }
});