window.YM = window.YM || {};

YM.getTargetFromUrl = function() {
    return new URL(window.location.href).searchParams.get('target');
};

YM.replaceBrowserUrl = function(target) {
    const url = new URL(window.location.href);
    const currentTarget = url.searchParams.get('target');
    const normalizedTarget = target ? YM.normalizeUrl(target) : target;
    if (normalizedTarget === currentTarget) return;
    if (normalizedTarget) {
        url.searchParams.set('target', normalizedTarget);
    } else {
        url.searchParams.delete('target');
    }
    window.history.replaceState({}, '', url);
};

YM.pushBrowserUrl = function(target) {
    const url = new URL(window.location.href);
    const currentTarget = url.searchParams.get('target');
    const normalizedTarget = target ? YM.normalizeUrl(target) : target;
    if (normalizedTarget === currentTarget) return;
    if (normalizedTarget) {
        url.searchParams.set('target', normalizedTarget);
    } else {
        url.searchParams.delete('target');
    }
    window.history.pushState({}, '', url);
};

YM.SELF_APP_PATH = '/yellow-mirror';

YM.isSelfAppUrl = function(urlString) {
    try {
        const url = new URL(urlString, window.location.origin);
        const path = url.pathname.replace(/\/+$/, '');
        return path === YM.SELF_APP_PATH;
    } catch {
        return false;
    }
};