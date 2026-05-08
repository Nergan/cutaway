self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Bypass any actual native traffic belonging to cutaway (snake, kanban, etc.)
    if (url.origin !== self.location.origin) return;
    const path = url.pathname;
    
    if (path.startsWith('/yellow_mirror/')) return;
    if (path.startsWith('/yellow-mirror/')) return; // Avoid infinite loops on the proxy API itself
    if (path.startsWith('/mainpage-backgrounds/')) return;
    if (path.startsWith('/evenfest/') || path.startsWith('/snake/') || path.startsWith('/toadbin/')) return;
    if (path.startsWith('/formular/') || path.startsWith('/markbin/') || path.startsWith('/kanban/')) return;
    if (path.startsWith('/foundry/') || path === '/' || path === '/api/track') return;

    // We catch requests like fetch('/api/user_info') made BY the iframe and rewrite them automatically.
    event.respondWith((async () => {
        const client = await clients.get(event.clientId);
        if (client && client.url) {
            const clientUrl = new URL(client.url);
            
            if (clientUrl.pathname.startsWith('/yellow-mirror/proxy/')) {
                const targetOriginStr = clientUrl.pathname.substring(21); // Strip /yellow-mirror/proxy/
                try {
                    const targetUrl = new URL(targetOriginStr);
                    const newUrl = `${targetUrl.origin}${url.pathname}${url.search}`;
                    
                    return fetch(`/yellow-mirror/proxy/${newUrl}`, {
                        method: event.request.method,
                        headers: event.request.headers,
                        body:['GET', 'HEAD'].includes(event.request.method) ? undefined : await event.request.blob(),
                        redirect: 'manual'
                    });
                } catch (e) {
                    console.error("YM SW Rewrite Error", e);
                }
            }
        }
        return fetch(event.request);
    })());
});