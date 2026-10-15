self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }
  const title = data.title || 'netlazy';
  const iconPath = data.icon || '/netlazy/static/push/share.png';
  const icon = iconPath.startsWith('http') ? iconPath : new URL(iconPath, self.location.origin).href;
  const options = {
    body: data.body || '',
    icon,
    badge: icon,
    tag: data.tag || 'netlazy-request',
    renotify: true,
    data: { open_path: data.open_path || '/netlazy/inbox' },
  };
  if (data.platform === 'android') options.vibrate = [80, 40, 80];
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const path = (event.notification.data && event.notification.data.open_path) || '/netlazy/inbox';
  const url = new URL(path, self.location.origin).href;
  event.waitUntil((async () => {
    const openClients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of openClients) {
      if (client.url.startsWith(self.location.origin) && 'focus' in client) {
        client.postMessage({ type: 'netlazy-open', path });
        return client.focus();
      }
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  })());
});
