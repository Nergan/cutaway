// --- AUTO CACHE REFRESHER ---
const APP_VERSION = '2.2.0';
if (localStorage.getItem('formular_version') !== APP_VERSION) {
    localStorage.setItem('formular_version', APP_VERSION);
    window.location.reload(true);
}

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Sortable JS
    try { 
        new Sortable(document.getElementById('sortableContainer'), {
            animation: 150,
            handle: '.drag-handle',
            ghostClass: 'sortable-ghost',
            multiDrag: true,
            multiDragKey: 'CTRL', 
            selectedClass: 'selected',
            fallbackTolerance: 3 
        });
    } catch(e) {}

    // 2. Initialize Module Systems
    window.Formular.initUploader();
    window.Formular.initLasso();
    window.Formular.initBulkActions();

    // 3. Prevent Data Loss
    window.addEventListener('beforeunload', (e) => {
        if (document.getElementById('sortableContainer').children.length > 0) { 
            e.preventDefault(); e.returnValue = ''; 
        }
    });

    // 4. Hotkeys Configuration
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        // CTRL+A 
        if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyA' || e.key.toLowerCase() === 'a')) {
            e.preventDefault(); 
            const cards = document.querySelectorAll('.file-card');
            if (cards.length > 0) {
                cards.forEach(c => c.classList.add('selected'));
                window.Formular.updateBulkPanel();
            }
        }
        
        // DELETE
        if (e.key === 'Delete' || e.key === 'Backspace') {
            const selectedCards = document.querySelectorAll('.file-card.selected');
            if (selectedCards.length > 0) {
                e.preventDefault();
                selectedCards.forEach(card => { if (card.doRemove) card.doRemove(); });
                window.Formular.updateBulkPanel();
            }
        }
        
        // ESCAPE
        if (e.key === 'Escape') {
            e.preventDefault();
            const selectedCards = document.querySelectorAll('.file-card.selected');
            if (selectedCards.length > 0) {
                selectedCards.forEach(card => card.classList.remove('selected'));
                window.Formular.updateBulkPanel();
            }
            document.querySelectorAll('.custom-select-options.open').forEach(el => {
                el.classList.remove('open');
                el.previousElementSibling.classList.remove('open');
                const card = el.closest('.file-card');
                if (card) card.classList.remove('dropdown-open');
            });
        }
    });

    // 5. Global Paste Listener
    document.addEventListener('paste', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        window.Formular.processClipboard(e);
    });

    // 6. Global Background Click logic
    document.addEventListener('click', (e) => {
        if (window.Formular.wasLassoSelecting) return; 
        
        if (!e.target.closest('.file-card') && !e.target.closest('.bulk-panel') && !e.target.closest('.fab') && !e.target.closest('.custom-select-wrapper')) {
            document.querySelectorAll('.file-card.selected').forEach(c => c.classList.remove('selected'));
            window.Formular.updateBulkPanel();
        }
        
        if (document.getElementById('sortableContainer').children.length === 0 && !e.target.closest('.fab') && !e.target.closest('.bulk-panel')) {
            document.getElementById('fileInput').click();
        }
    });

    document.getElementById('fabAdd').addEventListener('click', (e) => { 
        e.stopPropagation(); 
        document.getElementById('fileInput').click(); 
    });
});