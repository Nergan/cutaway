window.Formular = window.Formular || {};

window.Formular.initCustomSelect = function(selectEl) {
    if (selectEl.nextElementSibling && selectEl.nextElementSibling.classList.contains('custom-select-wrapper')) {
        selectEl.nextElementSibling.remove();
    }
    selectEl.style.display = 'none';
    
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrapper';
    
    const trigger = document.createElement('div');
    trigger.className = 'custom-select-trigger';
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    trigger.innerHTML = `<span>${selectedOpt ? selectedOpt.text : 'Target format...'}</span><i class="bi bi-chevron-down"></i>`;
    
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'custom-select-options';
    
    Array.from(selectEl.options).forEach(opt => {
        if (opt.disabled) return;
        const optDiv = document.createElement('div');
        optDiv.className = 'custom-option';
        optDiv.textContent = opt.text;
        optDiv.addEventListener('click', (e) => {
            e.stopPropagation();
            selectEl.value = opt.value;
            trigger.querySelector('span').textContent = opt.text;
            optionsContainer.classList.remove('open');
            trigger.classList.remove('open');
            
            const card = wrapper.closest('.file-card');
            if (card) card.classList.remove('dropdown-open');
            
            selectEl.dispatchEvent(new Event('change'));
        });
        optionsContainer.appendChild(optDiv);
    });
    
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelectorAll('.custom-select-options.open').forEach(el => {
            if (el !== optionsContainer) {
                el.classList.remove('open');
                el.previousElementSibling.classList.remove('open');
                const otherCard = el.closest('.file-card');
                if (otherCard) otherCard.classList.remove('dropdown-open');
            }
        });
        optionsContainer.classList.toggle('open');
        trigger.classList.toggle('open');
        
        const card = wrapper.closest('.file-card');
        if (card) card.classList.toggle('dropdown-open');
    });
    
    wrapper.appendChild(trigger);
    wrapper.appendChild(optionsContainer);
    selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
};

document.addEventListener('click', () => {
    document.querySelectorAll('.custom-select-options.open').forEach(el => {
        el.classList.remove('open');
        el.previousElementSibling.classList.remove('open');
        const card = el.closest('.file-card');
        if (card) card.classList.remove('dropdown-open');
    });
});