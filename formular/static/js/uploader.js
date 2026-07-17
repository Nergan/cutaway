window.Formular = window.Formular || {};

window.Formular.initUploader = function() {
    const fileInput = document.getElementById('fileInput');
    const sortableContainer = document.getElementById('sortableContainer');
    const dragOverlay = document.getElementById('dragOverlay');

    // Force Mobile OS to open File Explorer instead of Photo Library
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

        Array.from(validFiles).forEach((file) => {
            const formData = new FormData();
            formData.append('files', file);

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

            const xhr = new XMLHttpRequest();
            const cancelBtn = p.querySelector('.btn-remove');
            cancelBtn.addEventListener('click', (e) => {
                e.stopPropagation(); xhr.abort(); p.remove(); window.Formular.toggleUIState();
            });

            xhr.open('POST', './api/upload', true);
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = (e.loaded / e.total) * 90;
                    p.style.setProperty('--progress', `${percent}%`);
                }
            };

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    const data = JSON.parse(xhr.responseText);
                    const fileData = data.files[0];
                    if (fileData.error) {
                        window.Formular.Toast.show(`${fileData.filename}: ${fileData.error}`, 'error');
                        p.remove();
                    } else {
                        p.style.setProperty('--progress', '100%');
                        setTimeout(() => {
                            p.style.setProperty('--progress', '0%');
                            p.remove(); 
                            window.Formular.createCard(fileData); 
                        }, 400); 
                    }
                    window.Formular.toggleUIState();
                } else {
                    window.Formular.Toast.show(`Network error uploading ${file.name}.`, 'error');
                    p.remove(); window.Formular.toggleUIState();
                }
            };
            xhr.onerror = () => { 
                if (xhr.status === 0) {
                    window.Formular.Toast.show(`Cannot read "${file.name}". The file is missing.`, 'error');
                } else {
                    window.Formular.Toast.show(`Network error uploading ${file.name}.`, 'error'); 
                }
                p.remove(); window.Formular.toggleUIState(); 
            };
            xhr.send(formData);
        });
        window.Formular.toggleUIState();
    }
};