self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Completely ignore our app's core native assets
    if (url.origin === self.location.origin) {
        const path = url.pathname;
        if (
            path.startsWith('/yellow_mirror/') || 
            path.startsWith('/mainpage-backgrounds/') || 
            path === '/' || 
            path === '/api/track' ||
            path.startsWith('/evenfest/') || 
            path.startsWith('/snake/') || 
            path.startsWith('/toadbin/') || 
            path.startsWith('/formular/') || 
            path.startsWith('/markbin/') || 
            path.startsWith('/kanban/') || 
            path.startsWith('/foundry/')
        ) {
            return; // Let native cutaway requests pass untouched
        }
    }

    event.respondWith((async () => {
        // Find which client (iframe) made the request
        const client = await clients.get(event.clientId);
        
        // If the request comes from our proxy iframe, OR if the request is already trying to hit the proxy
        const isFromProxy = client && client.url.includes('/yellow-mirror/proxy/');
        const isTargetingProxy = event.request.url.includes('/yellow-mirror/proxy/');

        if (isFromProxy && !isTargetingProxy) {
            // THE FIX: The site tried to fetch a cross-origin resource directly (e.g., Twitch modules or MyIP images).
            // We forcefully reroute it through our proxy.
            const proxiedUrl = `/yellow-mirror/proxy/${event.request.url}`;
            
            const headers = new Headers(event.request.headers);
            // Delete browser-enforced origin to let our backend spoof it
            headers.delete('Origin');
            headers.delete('Referer');

            return fetch(proxiedUrl, {
                method: event.request.method,
                headers: headers,
                body: ['GET', 'HEAD'].includes(event.request.method) ? undefined : await event.request.blob(),
                redirect: 'manual'
            });
        }

        return fetch(event.request);
    })());
});