document.addEventListener('DOMContentLoaded', function() {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const downloadLink = document.getElementById('downloadLink');
    const downloadInfo = document.getElementById('downloadInfo');
    const convertBtn = document.getElementById('convertBtn');
    const fromFormat = document.getElementById('fromFormat');
    const toFormat = document.getElementById('toFormat');

    let selectedFile = null;
    let currentBlobUrl = null;

    // Drag and drop functionality
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Handle file selection
    function handleFileSelect(file) {
        selectedFile = file;
        fileInfo.innerHTML = `
            <div class="alert alert-success d-flex align-items-center" role="alert">
                <i class="bi bi-check-circle-fill me-2"></i>
                <div>
                    <strong>${file.name}</strong><br>
                    <small>${(file.size / 1024).toFixed(2)} KB • ${file.type || 'Unknown type'}</small>
                </div>
            </div>
        `;
        
        const ext = file.name.split('.').pop().toLowerCase();
        if (ext) {
            fromFormat.value = ext;
        }
    }

    // Convert button click
    convertBtn.addEventListener('click', async () => {
        if (!selectedFile) {
            alert('Please select a file first!');
            return;
        }

        if (fromFormat.value === 'Select Format' || toFormat.value === 'Select Format') {
            alert('Please select both source and target formats!');
            return;
        }

        convertBtn.disabled = true;
        convertBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Converting...';

        if (currentBlobUrl) {
            URL.revokeObjectURL(currentBlobUrl);
            currentBlobUrl = null;
        }

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('from_format', fromFormat.value);
        formData.append('to_format', toFormat.value);

        try {
            const response = await fetch('/api/convert', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                try {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || errorData.message || `Server error: ${response.status}`);
                } catch {
                    throw new Error(`Server error: ${response.status}`);
                }
            }

            const blob = await response.blob();
            
            let filename;
            const contentDisposition = response.headers.get('Content-Disposition');
            
            // Пытаемся извлечь имя файла из заголовка
            if (contentDisposition) {
                // Пробуем разные форматы заголовка
                let match = contentDisposition.match(/filename\*?=UTF-8''([^;]+)/i);
                if (match && match[1]) {
                    // Декодируем URL-encoded имя файла
                    filename = decodeURIComponent(match[1]);
                } else {
                    match = contentDisposition.match(/filename="?([^"]+)"?/i);
                    if (match && match[1]) {
                        filename = match[1];
                    } else {
                        // Генерируем имя файла на основе исходного
                        filename = selectedFile.name.replace(/\.[^/.]+$/, "") + `.${toFormat.value}`;
                    }
                }
            } else {
                // Генерируем имя файла на основе исходного
                filename = selectedFile.name.replace(/\.[^/.]+$/, "") + `.${toFormat.value}`;
            }
            
            currentBlobUrl = URL.createObjectURL(blob);
            
            downloadLink.href = currentBlobUrl;
            downloadLink.download = filename;
            downloadLink.classList.remove('d-none');
            
            downloadInfo.innerHTML = `
                <div class="alert alert-info d-flex align-items-center" role="alert">
                    <i class="bi bi-info-circle-fill me-2"></i>
                    <div>
                        Converted to <strong>${toFormat.value.toUpperCase()}</strong><br>
                        <small>Ready to download: ${filename}</small>
                    </div>
                </div>
            `;

        } catch (error) {
            console.error('Error:', error);
            downloadInfo.innerHTML = `
                <div class="alert alert-danger d-flex align-items-center" role="alert">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <div>Conversion failed: ${error.message}</div>
                </div>
            `;
            downloadLink.classList.add('d-none');
        } finally {
            convertBtn.disabled = false;
            convertBtn.innerHTML = '<i class="bi bi-lightning-charge me-2"></i>Convert';
        }
    });

    fromFormat.addEventListener('change', updateConversionDirection);
    toFormat.addEventListener('change', updateConversionDirection);

    function updateConversionDirection() {
        if (fromFormat.value !== 'Select Format' && toFormat.value !== 'Select Format') {
            const arrow = document.querySelector('.bi-arrow-right');
            arrow.classList.add('text-success');
            arrow.classList.remove('text-primary');
        } else {
            const arrow = document.querySelector('.bi-arrow-right');
            arrow.classList.remove('text-success');
            arrow.classList.add('text-primary');
        }
    }
    
    window.addEventListener('beforeunload', () => {
        if (currentBlobUrl) {
            URL.revokeObjectURL(currentBlobUrl);
        }
    });
});