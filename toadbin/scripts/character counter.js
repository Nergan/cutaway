document.addEventListener('DOMContentLoaded', function() {
    function updateCharCount() {
        const count = codeInput.value.length;
        charCount.textContent = `${count} character${count !== 1 ? 's' : ''}`;
    }
    updateCharCount();
    codeInput.addEventListener('input', updateCharCount);
});