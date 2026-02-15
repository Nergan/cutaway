document.addEventListener('DOMContentLoaded', function() {
    function updateCharCount() {
        let count = 0;
        if (window.codeMirrorEditor) {
            count = window.codeMirrorEditor.getValue().length;
        } else {
            const codeInput = document.getElementById('codeInput');
            if (codeInput) {
                count = codeInput.value.length;
            }
        }
        const charCount = document.getElementById('charCount');
        if (charCount) {
            charCount.textContent = `${count} character${count !== 1 ? 's' : ''}`;
        }
    }

    // Первоначальное обновление
    updateCharCount();

    // Подписка на события
    if (window.codeMirrorEditor) {
        window.codeMirrorEditor.on('change', updateCharCount);
    } else {
        const codeInput = document.getElementById('codeInput');
        if (codeInput) {
            codeInput.addEventListener('input', updateCharCount);
        }
    }
});