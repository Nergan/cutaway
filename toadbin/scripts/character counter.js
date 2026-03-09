document.addEventListener('DOMContentLoaded', () => {
    const codeInput = document.getElementById('codeInput');
    const charCount = document.getElementById('charCount');

    if (!codeInput || !charCount) {
        console.warn('Required elements not found for character counter.');
        return;
    }

    const updateCharCount = () => {
        const count = codeInput.value.length;
        charCount.textContent = `${count} character${count !== 1 ? 's' : ''}`;
    };

    updateCharCount();
    codeInput.addEventListener('input', updateCharCount);
});