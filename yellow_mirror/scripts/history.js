window.YM = window.YM || {};

YM.history = {
    push: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return;

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.pushState({ target: normalized }, '', url);

        YM.navigator.load(normalized);
    },

    replaceCurrent: function(target) {
        if (!target) return;
        const normalized = YM.normalizeUrl(target);
        const currentTarget = YM.getTargetFromUrl();
        if (normalized === currentTarget) return;

        const url = new URL(window.location.href);
        url.searchParams.set('target', normalized);
        window.history.replaceState({ target: normalized }, '', url);
    },

    onPopState: function(event) {
        const target = YM.getTargetFromUrl();
        if (target) {
            YM.navigator.load(target);
        } else {
            window.location.href = '/';
        }
    }
};