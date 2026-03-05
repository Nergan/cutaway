window.YM = window.YM || {};

YM.toast = {
    element: null,
    timeoutId: null,

    init: function() {
        this.element = document.getElementById('error-toast');
        if (!this.element) {
            this.element = document.createElement('div');
            this.element.id = 'error-toast';
            this.element.className = 'error-toast hidden';
            this.element.textContent = 'Sorry, it is impossible to access the site';
            document.body.appendChild(this.element);
        }
    },

    show: function(message, duration = 5000) {
        if (!this.element) return;
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }
        this.element.textContent = message;
        this.element.classList.remove('hidden');
        this.element.classList.add('visible');
        this.timeoutId = setTimeout(() => {
            this.hide();
        }, duration);
    },

    hide: function() {
        if (!this.element) return;
        this.element.classList.remove('visible');
        this.element.classList.add('hidden');
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    YM.toast.init();
});