window.Formular = window.Formular || {};

window.Formular.Toast = {
    show(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `custom-toast ${type}`;
        const text = document.createElement('span');
        text.textContent = message;
        toast.innerHTML = '<i class="bi bi-info-circle me-2"></i> ';
        toast.appendChild(text);
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-100%)';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
};

window.Formular.formatBytes = function (amount) {
    if (amount >= 1024 * 1024) return `${(amount / (1024 * 1024)).toFixed(1)} MiB`;
    if (amount >= 1024) return `${(amount / 1024).toFixed(1)} KiB`;
    return `${amount} B`;
};

window.Formular.toggleUIState = function() {
    const sortableContainer = document.getElementById('sortableContainer');
    const emptyState = document.getElementById('emptyState');
    const filesList = document.getElementById('filesList');
    const fabAdd = document.getElementById('fabAdd');
    
    if (sortableContainer.children.length > 0) {
        emptyState.style.display = 'none';
        filesList.style.display = 'block';
        fabAdd.style.display = 'flex';
    } else {
        emptyState.style.display = 'block';
        filesList.style.display = 'none';
        fabAdd.style.display = 'none';
        if (window.Formular.updateBulkPanel) window.Formular.updateBulkPanel();
    }
};