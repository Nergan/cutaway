self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Bypass parent domain resources
    if (url.origin !== self.location.origin) return;
    const path = url.pathname;
    
    if (path.startsWith('/yellow_mirror/') || path.startsWith('/yellow-mirror/')) return;
    if (path.startsWith('/mainpage-backgrounds/') || path === '/' || path === '/api/track') return;
    if (path.startsWith('/evenfest/') || path.startsWith('/snake/') || path.startsWith('/toadbin/')) return;
    if (path.startsWith('/formular/') || path.startsWith('/markbin/') || path.startsWith('/kanban/')) return;
    if (path.startsWith('/foundry/')) return;

    // Route root-relative SPA fetch calls back through the proxy
    event.respondWith((async () => {
        const client = await clients.get(event.clientId);
        if (client && client.url) {
            const clientUrl = new URL(client.url);
            
            if (clientUrl.pathname.includes('/yellow-mirror/proxy/')) {
                let targetOriginStr = clientUrl.pathname.split('/proxy/')[1] + clientUrl.search + clientUrl.hash;
                targetOriginStr = targetOriginStr.replace(/^(https?:)\/+(.*)/, "$1//$2"); // Handle missing slashes
                
                try {
                    const targetUrl = new URL(targetOriginStr);
                    const newUrl = `${targetUrl.origin}${url.pathname}${url.search}`;
                    
                    return fetch(`/yellow-mirror/proxy/${newUrl}`, {
                        method: event.request.method,
                        headers: event.request.headers,
                        body: ['GET', 'HEAD'].includes(event.request.method) ? undefined : await event.request.blob(),
                        redirect: 'manual'
                    });
                } catch (e) { console.error("YM SW Error", e); }
            }
        }
        return fetch(event.request);
    })());
});