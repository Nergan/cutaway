window.Formular = window.Formular || {};

window.Formular.createCard = function(file) {
    const sortableContainer = document.getElementById('sortableContainer');
    const sizeMB = (file.size / (1024*1024)).toFixed(2);
    let optionsHTML = '<option value="" disabled selected>Target format...</option>';
    file.allowed_targets.forEach(t => { optionsHTML += `<option value="${t}">${t.toUpperCase()}</option>`; });

    const localFile = window.Formular.LocalFiles ? window.Formular.LocalFiles[file.id] : null;
    const ext = (file.format || '').toLowerCase();
    
    const audioExts = ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac'];
    const archiveExts = ['zip', 'rar', '7z', 'tar', 'gz'];
    const codeExts = ['js', 'py', 'json', 'xml', 'yaml', 'yml', 'toml', 'html', 'css', 'sh', 'bat', 'cpp', 'c', 'cs', 'java', 'php', 'rb', 'go', 'rs'];
    const sheetExts = ['csv', 'xlsx', 'xls'];

    let initialFallback = `<div class="file-preview-fallback"><i class="bi bi-file-earmark-text"></i></div>`;
    if (audioExts.includes(ext)) {
        initialFallback = `<div class="file-preview-fallback"><i class="bi bi-music-note-beamed"></i></div>`;
    } else if (archiveExts.includes(ext)) {
        initialFallback = `<div class="file-preview-fallback"><i class="bi bi-file-earmark-zip"></i></div>`;
    } else if (codeExts.includes(ext)) {
        initialFallback = `<div class="file-preview-fallback"><i class="bi bi-code-slash"></i></div>`;
    } else if (sheetExts.includes(ext)) {
        initialFallback = `<div class="file-preview-fallback"><i class="bi bi-file-earmark-excel"></i></div>`;
    }

    const cardElement = document.createElement('div');
    cardElement.className = 'file-card';
    cardElement.id = `file-${file.id}`;
    cardElement.allowedTargets = file.allowed_targets; 
    
    cardElement.innerHTML = `
        <div class="drag-handle"><i class="bi bi-grip-vertical"></i></div>
        <div class="file-preview-wrapper" id="preview-wrap-${file.id}">
            ${initialFallback}
            <div class="card-visualizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>
        </div>
        <div class="file-info">
            <div class="file-name" title="${file.filename}">${file.filename}</div>
            <div class="file-meta">${sizeMB} MB • Detected: <strong>${file.format.toUpperCase()}</strong></div>
        </div>
        <div class="file-actions">
            <select class="gothic-select" id="target-${file.id}" data-original-format="${file.format}" data-file-id="${file.id}">${optionsHTML}</select>
            <button class="btn-custom" id="btn-convert-${file.id}" disabled>CONVERT</button>
            <a class="btn-custom btn-download" style="display:none;" id="btn-dl-${file.id}">DOWNLOAD</a>
            <button class="btn-custom btn-remove" id="btn-remove-${file.id}" title="Remove"><i class="bi bi-trash"></i></button>
        </div>
    `;
    sortableContainer.appendChild(cardElement);

    if (localFile) {
        const previewWrap = cardElement.querySelector(`#preview-wrap-${file.id}`);
        const url = URL.createObjectURL(localFile);
        if (localFile.type.startsWith('image/')) {
            previewWrap.innerHTML = `<img src="${url}" class="file-preview"><div class="card-visualizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>`;
        } else if (localFile.type.startsWith('video/')) {
            const tempVid = document.createElement('video');
            tempVid.src = url;
            tempVid.muted = true;
            tempVid.currentTime = 1.0; 
            tempVid.onloadeddata = () => {
                const canvas = document.createElement('canvas');
                canvas.width = tempVid.videoWidth;
                canvas.height = tempVid.videoHeight;
                canvas.getContext('2d').drawImage(tempVid, 0, 0, canvas.width, canvas.height);
                previewWrap.innerHTML = `<img src="${canvas.toDataURL()}" class="file-preview"><div class="card-visualizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>`;
            };
        } else if (localFile.type === 'application/pdf' || ext === 'pdf') {
            if (window.pdfjsLib) {
                localFile.arrayBuffer().then(arrayBuffer => {
                    return pdfjsLib.getDocument({ data: arrayBuffer }).promise;
                }).then(pdf => {
                    return pdf.getPage(1);
                }).then(page => {
                    const viewport = page.getViewport({ scale: 0.4 });
                    const canvas = document.createElement('canvas');
                    const context = canvas.getContext('2d');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;
                    return page.render({ canvasContext: context, viewport: viewport }).promise.then(() => canvas);
                }).then(canvas => {
                    previewWrap.innerHTML = `<img src="${canvas.toDataURL()}" class="file-preview"><div class="card-visualizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>`;
                }).catch(() => {
                    previewWrap.innerHTML = `<div class="file-preview-fallback"><i class="bi bi-file-earmark-pdf"></i></div><div class="card-visualizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>`;
                });
            } else {
                previewWrap.innerHTML = `<div class="file-preview-fallback"><i class="bi bi-file-earmark-pdf"></i></div><div class="card-visualizer"><div class="bar"></div><div class="bar"></div><div class="bar"></div></div>`;
            }
        }
    }

    const selectBox = cardElement.querySelector(`#target-${file.id}`);
    window.Formular.initCustomSelect(selectBox);

    const convertBtn = cardElement.querySelector(`#btn-convert-${file.id}`);
    const dlBtn = cardElement.querySelector(`#btn-dl-${file.id}`);
    const removeBtn = cardElement.querySelector(`#btn-remove-${file.id}`);

    let activeController = null;
    let progressInterval = null;
    let isConverting = false;

    selectBox.addEventListener('change', () => {
        // Validation sync handled globally in dropdown.js now, but convertBtn is auto enabled if valid
    });

    cardElement.doRemove = () => {
        if (activeController) activeController.abort();
        clearInterval(progressInterval);
        if (dlBtn.href) URL.revokeObjectURL(dlBtn.href);
        
        cardElement.dispatchEvent(new CustomEvent('card:removed'));
        
        if (window.Formular.LocalFiles) {
            delete window.Formular.LocalFiles[file.id];
        }
        window.dispatchEvent(new CustomEvent('formular:filesUpdated'));
        
        cardElement.remove();
        window.Formular.toggleUIState();
    };

    cardElement.getConvertedInfo = () => {
        if (dlBtn.style.display === 'inline-block' && dlBtn.href) {
            return { url: dlBtn.href, name: dlBtn.download };
        }
        return null;
    };

    cardElement.doConvert = async (targetFormat, aOpts = null, vOpts = null, cOpts = null, mergeId = null, mergeLoop = false) => {
        if (isConverting) return;
        isConverting = true;
        
        cardElement.dispatchEvent(new CustomEvent('card:converting'));

        if (activeController) activeController.abort();
        activeController = new AbortController();

        selectBox.value = targetFormat;
        const customTriggerSpan = cardElement.querySelector('.custom-select-trigger span');
        if (customTriggerSpan && targetFormat) {
            const isSparkling = customTriggerSpan.textContent.includes('✨');
            customTriggerSpan.textContent = targetFormat.toUpperCase() + (isSparkling ? ' ✨' : '');
        }
        
        convertBtn.disabled = true;
        convertBtn.innerText = 'PROCESSING...';
        convertBtn.style.background = 'var(--orange)';
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
        if (mergeId === null) mergeId = selectBox.dataset.mergeId;
        if (mergeLoop === false) mergeLoop = selectBox.dataset.mergeLoop;

        const fd = new FormData();
        fd.append('file_id', file.id);
        fd.append('to_format', targetFormat);
        if (aOpts) fd.append('audio_opts', aOpts);
        if (vOpts) fd.append('video_opts', vOpts);
        if (cOpts) fd.append('custom_ffmpeg', cOpts);
        if (mergeId) fd.append('merge_id', mergeId);
        if (mergeLoop) fd.append('merge_loop', mergeLoop);

        try {
            const response = await fetch('./api/convert', { method: 'POST', body: fd, signal: activeController.signal });
            
            if (response.status === 400 || response.status === 500) {
                const errorJson = await response.json();
                throw new Error(errorJson.detail || "Conversion error");
            }
            
            if (!response.ok) throw new Error("Conversion engine failure.");

            const blob = await response.blob();
            let outExt = targetFormat === 'gz' ? 'tar.gz' : targetFormat;
            let lastDotIndex = file.filename.lastIndexOf('.');
            let baseName = lastDotIndex === -1 ? file.filename : file.filename.substring(0, lastDotIndex);
            let outName = baseName + '.' + outExt;
            
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