window.Formular = window.Formular || {};

window.Formular.updateBulkPanel = function() {
    const selectedCards = document.querySelectorAll('.file-card.selected');
    const bulkPanel = document.getElementById('bulkPanel');
    const bulkTarget = document.getElementById('bulkTarget');
    const bulkConvertBtn = document.getElementById('bulkConvertBtn');
    const bulkZipBtn = document.getElementById('bulkZipBtn');
    const bulkMessage = document.getElementById('bulkMessage');
    const bulkCount = document.getElementById('bulkCount');
    
    if (selectedCards.length > 0) {
        bulkPanel.classList.add('active');
        document.body.classList.add('bulk-active');
        bulkCount.innerText = `${selectedCards.length} selected`;

        let commonFormats = null;
        let allConverted = true;

        selectedCards.forEach(card => {
            if (card.allowedTargets) {
                if (commonFormats === null) { commonFormats = [...card.allowedTargets]; } 
                else { commonFormats = commonFormats.filter(f => card.allowedTargets.includes(f)); }
            }
            if (!card.getConvertedInfo || !card.getConvertedInfo()) {
                allConverted = false;
            }
        });

        bulkZipBtn.disabled = !allConverted;
        bulkTarget.innerHTML = '<option value="" disabled selected>Target format...</option>';
        
        if (commonFormats && commonFormats.length > 0) {
            bulkTarget.style.display = 'inline-block';
            bulkMessage.style.display = 'none';
            commonFormats.forEach(f => { bulkTarget.innerHTML += `<option value="${f}">${f.toUpperCase()}</option>`; });
            window.Formular.initCustomSelect(bulkTarget);
            bulkTarget.nextElementSibling.style.display = 'block';
            bulkConvertBtn.disabled = true; 
        } else {
            if (bulkTarget.nextElementSibling && bulkTarget.nextElementSibling.classList.contains('custom-select-wrapper')) {
                bulkTarget.nextElementSibling.style.display = 'none';
            }
            bulkConvertBtn.disabled = true;
            bulkMessage.style.display = 'inline-block';
        }
    } else {
        bulkPanel.classList.remove('active');
        document.body.classList.remove('bulk-active');
        bulkConvertBtn.disabled = true;
    }
};

window.Formular.initBulkActions = function() {
    const bulkTarget = document.getElementById('bulkTarget');
    const bulkConvertBtn = document.getElementById('bulkConvertBtn');
    const bulkZipBtn = document.getElementById('bulkZipBtn');
    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');

    bulkTarget.addEventListener('change', () => { bulkConvertBtn.disabled = !bulkTarget.value; });

    bulkConvertBtn.addEventListener('click', () => {
        const format = bulkTarget.value;
        if (!format) return;
        
        const aOpts = bulkTarget.dataset.audioOpts || '';
        const vOpts = bulkTarget.dataset.videoOpts || '';
        const cOpts = bulkTarget.dataset.customFfmpeg || '';

        document.querySelectorAll('.file-card.selected').forEach(card => {
            if (card.doConvert) card.doConvert(format, aOpts, vOpts, cOpts);
        });
        window.Formular.updateBulkPanel();
    });

    bulkDeleteBtn.addEventListener('click', (e) => {
        e.stopPropagation(); 
        document.querySelectorAll('.file-card.selected').forEach(card => {
            if (card.doRemove) card.doRemove();
        });
        window.Formular.updateBulkPanel();
    });

    bulkZipBtn.addEventListener('click', async () => {
        const selectedCards = document.querySelectorAll('.file-card.selected');
        const zip = new JSZip();
        let hasFiles = false;

        const ogText = bulkZipBtn.innerHTML;
        bulkZipBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> ZIPPING...';
        bulkZipBtn.disabled = true;

        for (let card of selectedCards) {
            if (card.getConvertedInfo) {
                const info = card.getConvertedInfo();
                if (info && info.url) {
                    try {
                        const blob = await fetch(info.url).then(r => r.blob());
                        zip.file(info.name, blob);
                        hasFiles = true;
                    } catch (err) { console.error("Zip blob fetch failed", err); }
                }
            }
        }

        if (hasFiles) {
            const content = await zip.generateAsync({ type: "blob" });
            const url = URL.createObjectURL(content);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'converted.zip';
            a.click();
            URL.revokeObjectURL(url);
            window.Formular.Toast.show('ZIP downloaded successfully!', 'success');
        } else {
            window.Formular.Toast.show('No converted files available to ZIP in selection.', 'error');
        }

        bulkZipBtn.innerHTML = ogText;
        window.Formular.updateBulkPanel(); 
    });
};