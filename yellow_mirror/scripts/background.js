// yellow_mirror/scripts/background.js
window.YM = window.YM || {};

YM.background = {
    videoElement: null,

    init: function() {
        this.videoElement = document.getElementById('background-video');
        if (!this.videoElement) {
            console.warn('Background video element not found');
        }
    },

    show: function() {
        if (this.videoElement) {
            this.videoElement.style.display = 'block';
            // Перезапускаем видео, если оно остановилось
            this.videoElement.play().catch(e => console.warn('Autoplay failed:', e));
        }
    },

    hide: function() {
        if (this.videoElement) {
            this.videoElement.style.display = 'none';
            this.videoElement.pause(); // опционально, можно оставить на усмотрение
        }
    }
};

// Инициализация после загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    YM.background.init();
});