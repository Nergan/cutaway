window.Formular = window.Formular || {};

window.Formular.createCard = function(file) {
    const sortableContainer = document.getElementById('sortableContainer');
    const sizeMB = (file.size / (1024*1024)).toFixed(2);
    let optionsHTML = '<option value="" disabled selected>Target format...</option>';
    file.allowed_targets.forEach(t => { optionsHTML += `<option value="${t}">${t.toUpperCase()}</option>`; });

    const cardElement = document.createElement('div');
    cardElement.className = 'file-card';
    cardElement.id = `file-${file.id}`;
    cardElement.allowedTargets = file.allowed_targets; 
    
    cardElement.innerHTML = `
        <div class="drag-handle"><i class="bi bi-grip-vertical"></i></div>
        <div class="file-info">
            <div class="file-name" title="${file.filename}">${file.filename}</div>
            <div class="file-meta">${sizeMB} MB • Detected: <strong>${file.format.toUpperCase()}</strong></div>
        </div>
        <div class="file-actions">
            <select class="gothic-select" id="target-${file.id}">${optionsHTML}</select>
            <button class="btn-custom" id="btn-convert-${file.id}" disabled>CONVERT</button>
            <a class="btn-custom btn-download" style="display:none;" id="btn-dl-${file.id}">DOWNLOAD</a>
            <button class="btn-custom btn-remove" id="btn-remove-${file.id}" title="Remove"><i class="bi bi-trash"></i></button>
        </div>
    `;
    sortableContainer.appendChild(cardElement);

    const selectBox = cardElement.querySelector(`#target-${file.id}`);
    window.Formular.initCustomSelect(selectBox);

    const convertBtn = cardElement.querySelector(`#btn-convert-${file.id}`);
    const dlBtn = cardElement.querySelector(`#btn-dl-${file.id}`);
    const removeBtn = cardElement.querySelector(`#btn-remove-${file.id}`);

    let activeController = null;
    let progressInterval = null;
    let isConverting = false;

    selectBox.addEventListener('change', () => {
        convertBtn.disabled = false;
        if (activeController || dlBtn.style.display === 'inline-block') cardElement.doConvert(selectBox.value);
    });

    cardElement.doRemove = () => {
        if (activeController) activeController.abort();
        clearInterval(progressInterval);
        if (dlBtn.href) URL.revokeObjectURL(dlBtn.href);
        cardElement.remove();
        window.Formular.toggleUIState();
    };

    cardElement.getConvertedInfo = () => {
        if (dlBtn.style.display === 'inline-block' && dlBtn.href) {
            return { url: dlBtn.href, name: dlBtn.download };
        }
        return null;
    };

    cardElement.doConvert = async (targetFormat, aOpts = null, vOpts = null, cOpts = null) => {
        if (isConverting) return;
        isConverting = true;
        
        if (activeController) activeController.abort();
        activeController = new AbortController();

        selectBox.value = targetFormat;
        const customTriggerSpan = cardElement.querySelector('.custom-select-trigger span');
        if (customTriggerSpan && targetFormat) {
            // Keep any sparkling icons if they exist in the current text
            const isSparkling = customTriggerSpan.textContent.includes('✨');
            customTriggerSpan.textContent = targetFormat.toUpperCase() + (isSparkling ? ' ✨' : '');
        }
        
        convertBtn.disabled = true;
        convertBtn.innerText = 'PROCESSING...';
        dlBtn.style.display = 'none';
        cardElement.style.setProperty('--progress', '0%');
        clearInterval(progressInterval);
        window.Formular.updateBulkPanel(); 

        let progressValue = 0;
        progressInterval = setInterval(() => {
            progressValue += (90 - progressValue) * 0.1;
            cardElement.style.setProperty('--progress', `${progressValue}%`);
        }, 500);

        if (aOpts === null) aOpts = selectBox.dataset.audioOpts;
        if (vOpts === null) vOpts = selectBox.dataset.videoOpts;
        if (cOpts === null) cOpts = selectBox.dataset.customFfmpeg;

        const fd = new FormData();
        fd.append('file_id', file.id);
        fd.append('to_format', targetFormat);
        if (aOpts) fd.append('audio_opts', aOpts);
        if (vOpts) fd.append('video_opts', vOpts);
        if (cOpts) fd.append('custom_ffmpeg', cOpts);

        try {
            const response = await fetch('./api/convert', { method: 'POST', body: fd, signal: activeController.signal });
            
            if (response.status === 400 || response.status === 500) {
                const errorJson = await response.json();
                throw new Error(errorJson.detail || "Conversion error");
            }
            
            if (!response.ok) throw new Error("Conversion engine failure.");

            const blob = await response.blob();
            let outExt = targetFormat === 'gz' ? 'tar.gz' : targetFormat;
            let outName = file.filename.split('.').slice(0, -1).join('.') + '.' + outExt;
            
            clearInterval(progressInterval);
            cardElement.style.setProperty('--progress', '100%');
            
            convertBtn.innerText = 'RE-CONVERT';
            convertBtn.disabled = false;
            
            dlBtn.style.display = 'inline-block';
            if (dlBtn.href) URL.revokeObjectURL(dlBtn.href);
            dlBtn.href = URL.createObjectURL(blob);
            dlBtn.download = outName;
            
            activeController = null;
            isConverting = false;
            window.Formular.Toast.show(`Successfully forged: ${file.filename}`, 'success');
            window.Formular.updateBulkPanel(); 
        } catch(e) {
            isConverting = false;
            if (e.name !== 'AbortError') {
                clearInterval(progressInterval);
                cardElement.style.setProperty('--progress', '0%');
                convertBtn.disabled = false;
                convertBtn.innerText = 'RETRY';
                activeController = null;
                window.Formular.Toast.show(e.message || `Forge failed: ${file.filename}`, 'error');
            }
            window.Formular.updateBulkPanel();
        }
    };

    removeBtn.addEventListener('click', (e) => { e.stopPropagation(); cardElement.doRemove(); window.Formular.updateBulkPanel(); });
    convertBtn.addEventListener('click', (e) => { e.stopPropagation(); cardElement.doConvert(selectBox.value); });
};