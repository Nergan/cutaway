window.YM = window.YM || {};

YM.isValidIPv4 = function(str) {
    let s = str;
    if (s.endsWith('.')) {
        s = s.slice(0, -1);
    }
    const parts = s.split('.');
    if (parts.length !== 4) return false;
    return parts.every(part => {
        if (!/^\d+$/.test(part)) return false;
        const num = parseInt(part, 10);
        return num >= 0 && num <= 255;
    });
};

YM.isValidIPv6 = function(str) {
    let address = str.replace(/^\[|\]$/g, '');
    const ipv6Regex = /^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::([0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}$|^([0-9a-fA-F]{1,4}:){1,6}:$|^([0-9a-fA-F]{1,4}:){1,5}:[0-9a-fA-F]{1,4}$|^([0-9a-fA-F]{1,4}:){1,4}:[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4})?$|^([0-9a-fA-F]{1,4}:){1,3}:[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,2}$|^([0-9a-fA-F]{1,4}:){1,2}:[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,3}$|^[0-9a-fA-F]{1,4}::[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,4}$|^::[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){0,5}$|^[0-9a-fA-F]{1,4}$/;
    return ipv6Regex.test(address);
};

YM.isIP = function(str) {
    return YM.isValidIPv4(str) || YM.isValidIPv6(str);
};

YM.isValidDomain = function(host) {
    if (host === "localhost") return true;
    if (host.startsWith('.') || host.endsWith('.') || host.includes('..')) return false;
    const labels = host.split('.');
    if (labels.length < 2) return false;
    for (let i = 0; i < labels.length - 1; i++) {
        const label = labels[i];
        if (label.length === 0) return false;
        if (label.startsWith('-') || label.endsWith('-')) return false;
        if (!/^[a-zA-Z0-9-]+$/.test(label)) return false;
    }
    const tld = labels[labels.length - 1];
    return tld.length >= 2 && /^[a-zA-Z]+$/.test(tld);
};

YM.normalizeInput = function(str) {
    const slashIndex = str.indexOf('/');
    if (slashIndex !== -1 && slashIndex > 0 && str[slashIndex - 1] === '.') {
        return str.slice(0, slashIndex - 1) + str.slice(slashIndex);
    }
    if (str.endsWith('.')) {
        return str.slice(0, -1);
    }
    return str;
};

YM.isValidUrl = function(str) {
    const trimmed = str.trim();
    if (trimmed === '' || /\s/.test(trimmed)) return false;
    if (YM.isIP(trimmed)) return true;
    const normalized = YM.normalizeInput(trimmed);
    let url;
    try {
        const urlString = /^https?:\/\//i.test(normalized) ? normalized : 'https://' + normalized;
        url = new URL(urlString);
    } catch {
        return false;
    }
    const host = url.hostname;
    if (YM.isIP(host)) return true;
    return YM.isValidDomain(host);
};

YM.isSelfUrl = function(inputStr) {
    try {
        let urlString = inputStr.trim();
        if (!/^https?:\/\//i.test(urlString)) {
            urlString = 'https://' + urlString;
        }
        const inputUrl = new URL(urlString);
        const currentUrl = new URL(window.location.href);
        const sameHost = inputUrl.host.toLowerCase() === currentUrl.host.toLowerCase();
        const samePath = inputUrl.pathname === currentUrl.pathname;
        const sameSearch = inputUrl.search === currentUrl.search;
        const sameHash = inputUrl.hash === currentUrl.hash;
        return sameHost && samePath && sameSearch && sameHash;
    } catch {
        return false;
    }
};

YM.normalizeUrl = function(url) {
    if (!url) return url;
    return url.replace(/\/$/, '');
};

YM.simplifyUrl = function(url) {
    if (!url) return '';
    const normalized = YM.normalizeUrl(url);
    let simplified = normalized.replace(/^https?:\/\//i, '');
    simplified = simplified.replace(/^www\./i, '');
    return simplified;
};