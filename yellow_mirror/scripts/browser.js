window.YM = window.YM || {};

YM.getTargetFromUrl = function() {
    return new URL(window.location.href).searchParams.get('target');
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