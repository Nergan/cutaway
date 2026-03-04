window.YM = window.YM || {};

YM.splash = {
    targetX: 0,
    targetY: 0,
    currentX: 0,
    currentY: 0,
    rafId: null,
    maxOffset: 40,
    smoothing: 0.15,
    layers: [],

    init: function() {
        this.layers = document.querySelectorAll('.splash-layer');
        if (this.layers.length === 0) {
            console.warn('No splash layers found');
        }
    },

    show: function() {
        const el = YM.elements.splash;
        const iframe = YM.elements.iframe;
        if (!el || !iframe) return;
        el.style.display = 'block';
        iframe.style.pointerEvents = 'none';
        this.startTracking();
    },

    hide: function() {
        const el = YM.elements.splash;
        const iframe = YM.elements.iframe;
        if (!el || !iframe) return;
        el.style.display = 'none';
        iframe.style.pointerEvents = 'auto';
        this.stopTracking();
    },

    handleMouseMove: function(e) {
        if (!YM.elements.splash || YM.elements.splash.style.display === 'none') return;
        const x = (e.clientX / window.innerWidth) * 2 - 1;
        const y = (e.clientY / window.innerHeight) * 2 - 1;
        YM.splash.targetX = -x * YM.splash.maxOffset;
        YM.splash.targetY = -y * YM.splash.maxOffset;
    },

    updateLayerTransform: function() {
        if (!YM.elements.splash || YM.elements.splash.style.display === 'none') return;
        YM.splash.currentX += (YM.splash.targetX - YM.splash.currentX) * YM.splash.smoothing;
        YM.splash.currentY += (YM.splash.targetY - YM.splash.currentY) * YM.splash.smoothing;

        YM.splash.layers.forEach((layer, index) => {
            const factor = 0.5 + index * 0.3; // параллакс
            const x = YM.splash.currentX * factor;
            const y = YM.splash.currentY * factor;
            layer.style.transform = `translate(${x}%, ${y}%)`;
        });

        YM.splash.rafId = requestAnimationFrame(YM.splash.updateLayerTransform);
    },

    startTracking: function() {
        document.addEventListener('mousemove', YM.splash.handleMouseMove);
        if (YM.splash.rafId) cancelAnimationFrame(YM.splash.rafId);
        YM.splash.rafId = requestAnimationFrame(YM.splash.updateLayerTransform);
    },

    stopTracking: function() {
        document.removeEventListener('mousemove', YM.splash.handleMouseMove);
        if (YM.splash.rafId) {
            cancelAnimationFrame(YM.splash.rafId);
            YM.splash.rafId = null;
        }
        YM.splash.layers.forEach(layer => {
            layer.style.transform = 'translate(0%, 0%)';
        });
        YM.splash.currentX = 0;
        YM.splash.currentY = 0;
        YM.splash.targetX = 0;
        YM.splash.targetY = 0;
    }
};

document.addEventListener('DOMContentLoaded', () => {
    YM.splash.init();
});

window.addEventListener('resize', () => {
    YM.splash.targetX = 0;
    YM.splash.targetY = 0;
});