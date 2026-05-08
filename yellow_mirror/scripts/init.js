document.addEventListener('DOMContentLoaded', function() {
    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/yellow_mirror/scripts/sw.js', { scope: '/yellow-mirror/' })
            .then(() => console.log('Service Worker registered'))
            .catch(err => console.error('SW registration failed:', err));
    }
    // … rest of UI initialization unchanged …
});