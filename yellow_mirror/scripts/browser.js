// yellow_mirror/scripts/browser.js
window.YM = window.YM || {};

YM.getTargetFromUrl = function() {
    return new URL(window.location.href).searchParams.get('target');
};

// (Опционально) Оставляем для обратной совместимости, но не используем
// YM.pushBrowserUrl = function(target) { ... };
// YM.replaceBrowserUrl = function(target) { ... };