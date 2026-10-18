window.Formular = window.Formular || {};
window.Formular.LocalFiles = {}; // Cache to power local frontend previews

window.Formular.initUploader = function() {
    const fileInput = document.getElementById('fileInput');
    const sortableContainer = document.getElementById('sortableContainer');
    const dragOverlay = document.getElementById('dragOverlay');

    fileInput.setAttribute('multiple', 'multiple');
    fileInput.setAttribute('accept', '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.rtf,.odt,.epub,.djvu,.csv,.json,.yaml,.toml,.xml,.zip,.rar,.7z,.tar,.gz,text/*,application/*,image/*,audio/*,video/*');

    async function getFilesFromDataTransferItems(items) {
        let fileEntries = [];
        let queue = [];
        for (let i = 0; i < items.length; i++) {
            if (items[i].kind === 'file') {
                const entry = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
                if (entry) queue.push(entry);
                else {
                    const f = items[i].getAsFile();
                    if (f) fileEntries.push(f);
                }
            }
        }
        while (queue.length > 0) {
            let entry = queue.shift();
            if (entry.isFile) {
                const file = await new Promise(res => entry.file(res));
                fileEntries.push(file);
            } else if (entry.isDirectory) {
                let reader = entry.createReader();
                let entries;
                do {
                    entries = await new Promise(res => reader.readEntries(res));
                    queue.push(...entries);
                } while (entries.length > 0);
            }
        }
        return fileEntries;
    }

    let dragCounter = 0;
    document.body.addEventListener('dragenter', e => {
        if (e.dataTransfer.types && Array.from(e.dataTransfer.types).includes('Files')) {
            e.preventDefault(); dragCounter++; dragOverlay.classList.add('active');
        }
    });
    document.body.addEventListener('dragleave', e => {
        if (e.dataTransfer.types && Array.from(e.dataTransfer.types).includes('Files')) {
            e.preventDefault(); dragCounter--; if (dragCounter === 0) dragOverlay.classList.remove('active');
        }
    });
    document.body.addEventListener('dragover', e => e.preventDefault());
    
    document.body.addEventListener('drop', e => {
        e.preventDefault(); dragCounter = 0; dragOverlay.classList.remove('active');
        if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
            getFilesFromDataTransferItems(e.dataTransfer.items).then(files => {
                if (files.length > 0) processFiles(files);
            });
        } else if (e.dataTransfer.files.length > 0) {
            processFiles(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener('change', e => {
        if (e.target.files.length > 0) processFiles(e.target.files);
        fileInput.value = ''; 
    });

    window.Formular.processClipboard = async function(e) {
        if (e.clipboardData && e.clipboardData.items) {
            const files = await getFilesFromDataTransferItems(e.clipboardData.items);
            if (files.length > 0) {
                processFiles(files);
            } else {
                window.Formular.Toast.show('No valid files found in clipboard.', 'error');
            }
        }
    };

    function uploadFailure(xhr, file) {
        try {
            const data = JSON.parse(xhr.responseText);
            if (typeof data.detail === 'string' && data.detail) return data.detail;
        } catch (error) {}
        const max = window.Formular.maxFileBytes;
        if (xhr.status === 413 && max) {
            return `${file.name} is ${window.Formular.formatBytes(file.size)}. The maximum is ${window.Formular.formatBytes(max)}.`;
        }
        return `Network error uploading ${file.name}.`;
    }

    function sizeCeiling() {
        return window.Formular.maxStoredBytes || window.Formular.maxFileBytes;
    }

    async function prepareFile(file) {
        const max = sizeCeiling();
        let candidate = file;
        if (max && file.size > window.Formular.maxFileBytes && window.Formular.shrinkLossless) {
            try {
                const shrunk = await window.Formular.shrinkLossless(file);
                if (shrunk && shrunk.size < file.size) candidate = shrunk;
            } catch (error) {}
        }
        if (!max || candidate.size <= max) {
            if (candidate !== file) {
                window.Formular.Toast.show(
                    `${file.name} was reduced from ${window.Formular.formatBytes(file.size)} to ${window.Formular.formatBytes(candidate.size)} without a quality change.`,
                    'info',
                    8000
                );
            }
            return candidate;
        }
        window.Formular.Toast.show(
            `${file.name} is ${window.Formular.formatBytes(candidate.size)}. The maximum is ${window.Formular.formatBytes(max)}.`,
            'error',
            8000
        );
        return null;
    }

    async function processFiles(files) {
        let validFiles = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            try {
                await file.slice(0, 1).arrayBuffer();
                validFiles.push(file);
            } catch(e) {
                window.Formular.Toast.show(`Cannot read "${file.name}". The file is missing.`, 'error');
            }
        }

        if (validFiles.length === 0) return;

        const ready = [];
        for (const file of validFiles) {
            const prepared = await prepareFile(file);
            if (prepared) ready.push(prepared);
        }
        if (ready.length === 0) return;

        ready.forEach((file) => {
            const p = document.createElement('div');
            p.className = 'file-card';
            p.innerHTML = `
                <div class="drag-handle"><i class="bi bi-grip-vertical"></i></div>
                <div class="file-info">
                    <div class="file-name" title="${file.name}">${file.name}</div>
                    <div class="file-meta">Uploading & Analyzing...</div>
                </div>
                <div class="file-actions">
                    <button class="btn-custom btn-remove" title="Cancel Upload"><i class="bi bi-x-lg"></i></button>
                </div>
            `;
            sortableContainer.appendChild(p);
            const cancelBtn = p.querySelector('.btn-remove');
            const single = window.Formular.maxFileBytes;
            const send = single && file.size > single ? sendInPieces(file, p, cancelBtn) : sendWhole(file, p, cancelBtn);
            send.catch(() => {});
        });
        window.Formular.toggleUIState();
    }

    function acceptStored(file, card, payload) {
        const fileData = payload.files[0];
        if (!fileData || fileData.error) {
            window.Formular.Toast.show(`${file.name}: ${(fileData && fileData.error) || 'Upload failed.'}`, 'error', 8000);
            card.remove();
            window.Formular.toggleUIState();
            return;
        }
        window.Formular.LocalFiles[fileData.id] = file;
        window.dispatchEvent(new CustomEvent('formular:filesUpdated'));
        card.style.setProperty('--progress', '100%');
        setTimeout(() => {
            card.style.setProperty('--progress', '0%');
            card.remove();
            window.Formular.createCard(fileData);
        }, 400);
        window.Formular.toggleUIState();
    }

    function sendWhole(file, card, cancelBtn) {
        const formData = new FormData();
        formData.append('files', file);
        const xhr = new XMLHttpRequest();
        cancelBtn.addEventListener('click', (e) => {
            e.stopPropagation(); xhr.abort(); card.remove(); window.Formular.toggleUIState();
        });
        xhr.open('POST', './api/upload', true);
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) card.style.setProperty('--progress', `${(e.loaded / e.total) * 90}%`);
        };
        return new Promise((resolve) => {
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    acceptStored(file, card, JSON.parse(xhr.responseText));
                } else {
                    window.Formular.Toast.show(uploadFailure(xhr, file), 'error', 8000);
                    card.remove();
                    window.Formular.toggleUIState();
                }
                resolve();
            };
            xhr.onerror = () => {
                window.Formular.Toast.show(
                    xhr.status === 0 ? `Cannot read "${file.name}". The file is missing.` : `Network error uploading ${file.name}.`,
                    'error'
                );
                card.remove();
                window.Formular.toggleUIState();
                resolve();
            };
            xhr.send(formData);
        });
    }

    async function sendInPieces(file, card, cancelBtn) {
        const controller = new AbortController();
        let uploadId = null;
        cancelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            controller.abort();
            if (uploadId) fetch(`./api/uploads/${uploadId}`, { method: 'DELETE' }).catch(() => {});
            card.remove();
            window.Formular.toggleUIState();
        });
        try {
            const opened = await fetch('./api/uploads', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: file.name, size: file.size }),
                signal: controller.signal,
            });
            if (!opened.ok) throw opened;
            const info = await opened.json();
            uploadId = info.id;
            const piece = info.chunk_bytes;
            let sent = 0;
            for (let index = 0; sent < file.size; index += 1) {
                const slice = file.slice(sent, sent + piece);
                const written = await fetch(`./api/uploads/${uploadId}/${index}`, {
                    method: 'PUT',
                    body: slice,
                    signal: controller.signal,
                });
                if (!written.ok) throw written;
                sent += slice.size;
                card.style.setProperty('--progress', `${(sent / file.size) * 90}%`);
            }
            const finished = await fetch(`./api/uploads/${uploadId}/complete`, {
                method: 'POST',
                signal: controller.signal,
            });
            if (!finished.ok) throw finished;
            acceptStored(file, card, await finished.json());
        } catch (error) {
            if (controller.signal.aborted) return;
            let detail = `Network error uploading ${file.name}.`;
            if (error && typeof error.json === 'function') {
                try {
                    const body = await error.json();
                    if (body && body.detail) detail = body.detail;
                } catch (parseError) {}
            }
            window.Formular.Toast.show(detail, 'error', 8000);
            card.remove();
            window.Formular.toggleUIState();
        }
    }
};