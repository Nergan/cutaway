window.Formular = window.Formular || {};

window.Formular.initLasso = function() {
    let isSelecting = false;
    let wasSelecting = false;
    let startX, startY;
    let lastClientX, lastClientY;
    let selectionBox = null;
    let initiallySelected = new Set();
    
    window.Formular.wasLassoSelecting = false;

    // Helper to extract coordinates from both Mouse and Touch events seamlessly
    function getCoords(e) {
        if (e.touches && e.touches.length > 0) {
            return {
                clientX: e.touches[0].clientX,
                clientY: e.touches[0].clientY,
                pageX: e.touches[0].pageX,
                pageY: e.touches[0].pageY
            };
        }
        return { clientX: e.clientX, clientY: e.clientY, pageX: e.pageX, pageY: e.pageY };
    }

    function handleStart(e) {
        if (e.type === 'mousedown' && e.button !== 0) return; 
        const sortableContainer = document.getElementById('sortableContainer');
        if (e.target.closest('.file-card') || e.target.closest('.bulk-panel') || 
            e.target.closest('.fab') || e.target.closest('.custom-select-wrapper') || 
            sortableContainer.children.length === 0) return;

        isSelecting = true;
        wasSelecting = false;
        window.Formular.wasLassoSelecting = false;
        
        const coords = getCoords(e);
        startX = coords.pageX;
        startY = coords.pageY;
        lastClientX = coords.clientX;
        lastClientY = coords.clientY;

        if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
            document.querySelectorAll('.file-card.selected').forEach(c => c.classList.remove('selected'));
            initiallySelected.clear();
        } else {
            document.querySelectorAll('.file-card.selected').forEach(c => initiallySelected.add(c));
        }
    }

    document.addEventListener('mousedown', handleStart);
    document.addEventListener('touchstart', handleStart, { passive: true });

    function updateLasso() {
        if (!isSelecting) return;
        const currentX = lastClientX + window.scrollX;
        const currentY = lastClientY + window.scrollY;

        if (!selectionBox) {
            if (Math.abs(currentX - startX) > 3 || Math.abs(currentY - startY) > 3) {
                selectionBox = document.createElement('div');
                selectionBox.className = 'selection-box';
                document.body.appendChild(selectionBox); 
                document.body.classList.add('is-selecting');
                wasSelecting = true;
                window.Formular.wasLassoSelecting = true;
            } else return;
        }

        const left = Math.min(startX, currentX);
        const top = Math.min(startY, currentY);
        const width = Math.abs(startX - currentX);
        const height = Math.abs(startY - currentY);

        selectionBox.style.left = `${left}px`;
        selectionBox.style.top = `${top}px`;
        selectionBox.style.width = `${width}px`;
        selectionBox.style.height = `${height}px`;

        const boxRect = selectionBox.getBoundingClientRect();
        
        document.querySelectorAll('.file-card').forEach(card => {
            const cardRect = card.getBoundingClientRect();
            const isIntersecting = !(boxRect.right < cardRect.left || boxRect.left > cardRect.right || 
                                     boxRect.bottom < cardRect.top || boxRect.top > cardRect.bottom);
            
            if (isIntersecting || initiallySelected.has(card)) card.classList.add('selected');
            else card.classList.remove('selected');
        });
        window.Formular.updateBulkPanel();
    }

    function handleMove(e) {
        if (!isSelecting) return;
        if (e.type === 'mousemove' && e.buttons !== 1) { finishSelection(); return; }
        
        // Prevent screen scrolling while actively drawing the lasso on mobile
        if (e.type === 'touchmove') e.preventDefault();

        const coords = getCoords(e);
        lastClientX = coords.clientX;
        lastClientY = coords.clientY;
        updateLasso();
    }

    document.addEventListener('mousemove', handleMove);
    // passive: false is REQUIRED to allow e.preventDefault() to stop mobile scrolling
    document.addEventListener('touchmove', handleMove, { passive: false });

    window.addEventListener('scroll', () => { if (isSelecting) updateLasso(); });

    function finishSelection() {
        if (isSelecting) {
            isSelecting = false;
            document.body.classList.remove('is-selecting');
            if (selectionBox) { selectionBox.remove(); selectionBox = null; }
            window.Formular.updateBulkPanel();
            setTimeout(() => { wasSelecting = false; window.Formular.wasLassoSelecting = false; }, 100);
        }
    }

    window.addEventListener('mouseup', finishSelection);
    window.addEventListener('touchend', finishSelection);
    window.addEventListener('touchcancel', finishSelection);
};