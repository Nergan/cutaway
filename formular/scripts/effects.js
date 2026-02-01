// Formular - Simplified Effects Script
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const convertBtn = document.getElementById('convertBtn');
    const fromFormat = document.getElementById('fromFormat');
    const toFormat = document.getElementById('toFormat');
    const downloadLink = document.getElementById('downloadLink');
    const downloadZone = document.getElementById('downloadZone');
    
    // Initialize basic effects
    initBasicEffects();
    
    // File input change handler
    fileInput.addEventListener('change', handleFileSelect);
    
    // Conversion button click effect
    convertBtn.addEventListener('click', function() {
        if (fileInput.files.length > 0) {
            simulateConversion();
        }
    });
    
    // Functions
    function initBasicEffects() {
        // Add hover effects for upload zone
        uploadZone.addEventListener('mouseenter', function() {
            this.style.borderColor = 'var(--orange)';
        });
        
        uploadZone.addEventListener('mouseleave', function() {
            if (!this.classList.contains('dragover')) {
                this.style.borderColor = 'var(--light-gray)';
            }
        });
        
        // Add click effect for buttons
        const buttons = document.querySelectorAll('.btn');
        buttons.forEach(btn => {
            btn.addEventListener('click', function(e) {
                // Create ripple effect
                const ripple = document.createElement('span');
                const rect = this.getBoundingClientRect();
                const size = Math.max(rect.width, rect.height);
                const x = e.clientX - rect.left - size / 2;
                const y = e.clientY - rect.top - size / 2;
                
                ripple.style.position = 'absolute';
                ripple.style.width = size + 'px';
                ripple.style.height = size + 'px';
                ripple.style.left = x + 'px';
                ripple.style.top = y + 'px';
                ripple.style.backgroundColor = 'rgba(255, 255, 255, 0.3)';
                ripple.style.borderRadius = '50%';
                ripple.style.transform = 'scale(0)';
                ripple.style.transition = 'transform 0.5s ease-out, opacity 0.5s ease-out';
                
                this.style.position = 'relative';
                this.style.overflow = 'hidden';
                this.appendChild(ripple);
                
                setTimeout(() => {
                    ripple.style.transform = 'scale(4)';
                    ripple.style.opacity = '0';
                }, 10);
                
                setTimeout(() => {
                    if (ripple.parentNode === this) {
                        this.removeChild(ripple);
                    }
                }, 600);
            });
        });
        
        // Format selection effects
        fromFormat.addEventListener('change', function() {
            if (this.value !== 'Select Format') {
                this.style.borderColor = 'var(--orange)';
                updateConvertButtonState();
            }
        });
        
        toFormat.addEventListener('change', function() {
            if (this.value !== 'Select Format') {
                this.style.borderColor = 'var(--orange)';
                updateConvertButtonState();
            }
        });
    }
    
    function handleFileSelect() {
        const fileInfo = document.getElementById('fileInfo');
        
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            const fileSize = (file.size / 1024 / 1024).toFixed(2);
            
            fileInfo.innerHTML = `
                <div class="text-center">
                    <i class="bi bi-file-earmark-text text-orange me-2"></i>
                    <strong class="gothic-text">${file.name}</strong>
                    <div class="small text-muted mt-1">${fileSize} MB</div>
                </div>
            `;
            
            // Update status dot
            document.querySelector('.status-dot.ready').style.backgroundColor = 'var(--orange)';
            
            updateConvertButtonState();
        }
    }
    
    function updateConvertButtonState() {
        const hasFile = fileInput.files.length > 0;
        const fromSelected = fromFormat.value !== 'Select Format';
        const toSelected = toFormat.value !== 'Select Format';
        
        if (hasFile && fromSelected && toSelected) {
            convertBtn.disabled = false;
            convertBtn.style.opacity = '1';
            convertBtn.style.cursor = 'pointer';
        } else {
            convertBtn.disabled = true;
            convertBtn.style.opacity = '0.6';
            convertBtn.style.cursor = 'not-allowed';
        }
    }
    
    function simulateConversion() {
        // Update status
        document.querySelector('.status-dot.ready').style.backgroundColor = 'var(--text-muted)';
        document.querySelector('.status-dot.processing').style.backgroundColor = 'var(--orange)';
        
        // Update button state
        convertBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Processing...';
        convertBtn.disabled = true;
        convertBtn.style.opacity = '0.6';
        
        // Simulate processing time (2 seconds)
        setTimeout(() => {
            // Update status
            document.querySelector('.status-dot.processing').style.backgroundColor = 'var(--text-muted)';
            document.querySelector('.status-dot.complete').style.backgroundColor = 'var(--orange)';
            
            // Show download button
            const fileName = fileInput.files[0].name.replace(/\.[^/.]+$/, "") + '.pdf';
            downloadLink.classList.remove('d-none');
            downloadLink.href = '#';
            downloadLink.download = fileName;
            downloadLink.innerHTML = `<i class="bi bi-download me-2"></i>Download ${fileName}`;
            
            // Update download info
            const downloadInfo = document.getElementById('downloadInfo');
            downloadInfo.innerHTML = `
                <div class="text-center">
                    <i class="bi bi-check-circle text-orange me-2"></i>
                    <span class="gothic-text">Conversion complete</span>
                    <div class="small text-muted mt-1">Ready for download</div>
                </div>
            `;
            
            // Highlight download zone
            downloadZone.style.borderColor = 'var(--orange)';
            downloadZone.style.backgroundColor = 'rgba(255, 107, 53, 0.05)';
            
            // Reset convert button
            convertBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-2"></i>Convert';
            convertBtn.disabled = false;
            convertBtn.style.opacity = '1';
            
        }, 2000);
    }
    
    // Initialize convert button state
    updateConvertButtonState();
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl + O to open file dialog
        if ((e.ctrlKey || e.metaKey) && e.key === 'o') {
            e.preventDefault();
            fileInput.click();
        }
        
        // Enter to convert if button is enabled
        if (e.key === 'Enter' && !convertBtn.disabled) {
            e.preventDefault();
            convertBtn.click();
        }
    });
    
    // Add text-orange class
    const style = document.createElement('style');
    style.textContent = `
        .text-orange { color: var(--orange) !important; }
    `;
    document.head.appendChild(style);
});