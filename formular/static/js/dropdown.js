window.Formular = window.Formular || {};

function formatTrimTime(seconds) {
    if (isNaN(seconds)) return "00:00:00";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

window.Formular.initCustomSelect = function(selectEl) {
    if (selectEl.nextElementSibling && selectEl.nextElementSibling.classList.contains('custom-select-wrapper')) {
        selectEl.nextElementSibling.remove();
    }
    selectEl.style.display = 'none';
    
    const origFmt = selectEl.dataset.originalFormat || '';
    const fileId = selectEl.dataset.fileId;
    
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrapper';
    
    const trigger = document.createElement('div');
    trigger.className = 'custom-select-trigger';
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    trigger.innerHTML = `<span>${selectedOpt && selectedOpt.value ? selectedOpt.text : 'Target format...'}</span><i class="bi bi-chevron-down"></i>`;
    
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'custom-select-options advanced-dropdown';
    
    optionsContainer.addEventListener('click', e => e.stopPropagation());
    optionsContainer.addEventListener('mousedown', e => e.stopPropagation());

    // Removed the "None" buttons in favor of clicking active styles to toggle them off
    optionsContainer.innerHTML = `
        <div class="formats-grid"></div>
        <div class="media-settings" style="display: none;">
            
            <div class="vt-wrapper" style="display:none;">
                <label>Trim Timeline:</label>
                <div class="vt-track">
                    <div class="vt-range"></div>
                    <div class="vt-handle vt-left" data-dir="left"></div>
                    <div class="vt-handle vt-right" data-dir="right"></div>
                </div>
                <div class="vt-time-display">00:00:00 - 00:00:00</div>
            </div>

            <div class="settings-tabs">
                <div class="tab tab-audio" data-tab="audio">Audio</div>
                <div class="tab tab-video" data-tab="video">Video/Img</div>
                <div class="tab tab-custom" data-tab="custom">Custom</div>
            </div>
            
            <div class="tab-content audio-tab" style="display:none;">
                <div class="preset-btns">
                    <button class="btn-preset" data-preset="slowed">Slow+Reverb</button>
                    <button class="btn-preset" data-preset="nightcore">Nightcore</button>
                </div>
                <div class="slider-group">
                    <label>Tempo: <span class="val">1.0</span>x</label>
                    <input type="range" class="s-tempo" min="0.5" max="2.0" step="0.05" value="1.0">
                </div>
                <div class="slider-group">
                    <label>Reverb: <span class="val">0</span>%</label>
                    <input type="range" class="s-reverb" min="0" max="100" step="5" value="0">
                </div>
                <div class="slider-group">
                    <label>Bass: <span class="val">0</span> dB</label>
                    <input type="range" class="s-bass" min="-20" max="20" step="1" value="0">
                </div>
            </div>
            
            <div class="tab-content video-tab" style="display:none;">
                <div class="vc-wrapper" style="display:none;">
                    <label>Visual Crop Tool:</label>
                    <div class="vc-container">
                        <div class="vc-media-container" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center;"></div>
                        <div class="vc-crop-box">
                            <div class="vc-handle vc-n" data-dir="n"></div>
                            <div class="vc-handle vc-s" data-dir="s"></div>
                            <div class="vc-handle vc-e" data-dir="e"></div>
                            <div class="vc-handle vc-w" data-dir="w"></div>
                            <div class="vc-handle vc-nw" data-dir="nw"></div>
                            <div class="vc-handle vc-ne" data-dir="ne"></div>
                            <div class="vc-handle vc-sw" data-dir="sw"></div>
                            <div class="vc-handle vc-se" data-dir="se"></div>
                        </div>
                    </div>
                </div>

                <div class="flex-row">
                    <div style="flex:1;">
                        <label>Resize (WxH):</label>
                        <input type="text" class="v-resize custom-input" placeholder="e.g. 1920x1080">
                    </div>
                    <div style="flex:1;">
                        <label>Crop (W:H:X:Y):</label>
                        <input type="text" class="v-crop custom-input" placeholder="e.g. 100:100:0:0">
                    </div>
                </div>
                
                <label>Style Filter:</label>
                <div class="filter-chips">
                    <div class="f-chip" data-val="grayscale">Grayscale</div>
                    <div class="f-chip" data-val="sepia">Sepia</div>
                    <div class="f-chip" data-val="invert">Invert</div>
                </div>
            </div>
            
            <div class="tab-content custom-tab" style="display:none;">
                <label>Custom FFmpeg Flags:</label>
                <textarea class="c-flags custom-input" placeholder="-vf scale=320:-1"></textarea>
            </div>
        </div>
        <button class="btn-custom btn-apply" style="width: 100%; margin-top: 10px;">APPLY</button>
    `;

    const grid = optionsContainer.querySelector('.formats-grid');
    const mediaFormats = ['mp4','webm','gif','mp3','wav','ogg','jpg','png','webp'];
    const audioOnly = ['mp3','wav','ogg'];
    const imageOnly = ['jpg','png','webp','svg'];
    let currentSelectedFormat = selectEl.value;

    function updateTabVisibility(format) {
        const isMedia = mediaFormats.includes(format);
        optionsContainer.querySelector('.media-settings').style.display = isMedia ? 'block' : 'none';
        
        if (isMedia) {
            const tabAudio = optionsContainer.querySelector('.tab-audio');
            const tabVideo = optionsContainer.querySelector('.tab-video');
            
            if (audioOnly.includes(format)) {
                tabAudio.style.display = 'block';
                tabVideo.style.display = 'none';
                tabAudio.click();
            } else if (imageOnly.includes(format)) {
                tabAudio.style.display = 'none';
                tabVideo.style.display = 'block';
                tabVideo.click();
            } else {
                tabAudio.style.display = 'block';
                tabVideo.style.display = 'block';
                tabVideo.click();
            }
        }
    }

    Array.from(selectEl.options).forEach(opt => {
        if (opt.disabled || opt.value === "") return;
        const optDiv = document.createElement('div');
        optDiv.className = 'format-chip' + (currentSelectedFormat === opt.value ? ' active' : '');
        
        const isOriginal = (opt.value === origFmt);
        optDiv.innerHTML = isOriginal ? `${opt.text} <i class="bi bi-stars" style="color:var(--orange);"></i>` : opt.text;
        
        optDiv.dataset.value = opt.value;
        optDiv.addEventListener('click', (e) => {
            e.stopPropagation();
            grid.querySelectorAll('.format-chip').forEach(c => c.classList.remove('active'));
            optDiv.classList.add('active');
            currentSelectedFormat = opt.value;
            updateTabVisibility(opt.value);
        });
        grid.appendChild(optDiv);
    });

    const localFile = window.Formular.LocalFiles ? window.Formular.LocalFiles[fileId] : null;
    let visualCropperActive = false;
    let mediaDuration = 0;
    let currentTrimStart = 0;
    let currentTrimEnd = 0;

    const vtWrapper = optionsContainer.querySelector('.vt-wrapper');
    const vtTrack = optionsContainer.querySelector('.vt-track');
    const vtRange = optionsContainer.querySelector('.vt-range');
    const vtLeft = optionsContainer.querySelector('.vt-left');
    const vtRight = optionsContainer.querySelector('.vt-right');
    const vtTimeDisplay = optionsContainer.querySelector('.vt-time-display');

    function updateTrimUI() {
        if (mediaDuration === 0) return;
        const leftPercent = (currentTrimStart / mediaDuration) * 100;
        const rightPercent = (currentTrimEnd / mediaDuration) * 100;
        
        vtLeft.style.left = `${leftPercent}%`;
        vtRight.style.left = `${rightPercent}%`;
        
        vtRange.style.left = `${leftPercent}%`;
        vtRange.style.width = `${rightPercent - leftPercent}%`;
        
        vtTimeDisplay.textContent = `${formatTrimTime(currentTrimStart)} - ${formatTrimTime(currentTrimEnd)}`;
    }

    let isTrimming = false;
    let activeTrimHandle = null;

    vtLeft.addEventListener('mousedown', () => { isTrimming = true; activeTrimHandle = 'left'; });
    vtRight.addEventListener('mousedown', () => { isTrimming = true; activeTrimHandle = 'right'; });

    if (localFile) {
        const localFileUrl = URL.createObjectURL(localFile);
        
        if (localFile.type.startsWith('video/') || localFile.type.startsWith('audio/')) {
            vtWrapper.style.display = 'block';
            const testMedia = document.createElement(localFile.type.startsWith('video/') ? 'video' : 'audio');
            testMedia.src = localFileUrl;
            testMedia.onloadedmetadata = () => {
                mediaDuration = testMedia.duration;
                currentTrimEnd = mediaDuration;
                updateTrimUI();
            };
        }

        if (localFile.type.startsWith('video/') || localFile.type.startsWith('image/')) {
            const vcWrapper = optionsContainer.querySelector('.vc-wrapper');
            const vcContainer = optionsContainer.querySelector('.vc-container');
            const vcMediaContainer = optionsContainer.querySelector('.vc-media-container');
            const vcCropBox = optionsContainer.querySelector('.vc-crop-box');
            const cropInput = optionsContainer.querySelector('.v-crop');
            
            vcWrapper.style.display = 'block';
            let originalMediaWidth = 0;
            let originalMediaHeight = 0;
            let mediaEl = document.createElement(localFile.type.startsWith('video/') ? 'video' : 'img');
            
            if (localFile.type.startsWith('video/')) {
                mediaEl.autoplay = true; mediaEl.muted = true; mediaEl.loop = true;
                mediaEl.className = 'vc-media';
                mediaEl.src = localFileUrl;
                mediaEl.onloadedmetadata = () => {
                    originalMediaWidth = mediaEl.videoWidth;
                    originalMediaHeight = mediaEl.videoHeight;
                    visualCropperActive = true;
                };
            } else {
                mediaEl.className = 'vc-media';
                mediaEl.src = localFileUrl;
                mediaEl.onload = () => {
                    originalMediaWidth = mediaEl.naturalWidth;
                    originalMediaHeight = mediaEl.naturalHeight;
                    visualCropperActive = true;
                };
            }
            vcMediaContainer.appendChild(mediaEl);

            let isDragging = false;
            let isResizing = false;
            let currentHandle = null;
            let startX, startY, startBoxLeft, startBoxTop, startBoxWidth, startBoxHeight;
            
            function updateCropInput() {
                if (!visualCropperActive || originalMediaWidth === 0) return;
                const boxLeft = parseFloat(vcCropBox.style.left || 0);
                const boxTop = parseFloat(vcCropBox.style.top || 0);
                const boxWidth = parseFloat(vcCropBox.style.width || 100);
                const boxHeight = parseFloat(vcCropBox.style.height || 100);
                
                const crop_w = Math.max(2, Math.round((boxWidth / 100) * originalMediaWidth));
                const crop_h = Math.max(2, Math.round((boxHeight / 100) * originalMediaHeight));
                const crop_x = Math.max(0, Math.round((boxLeft / 100) * originalMediaWidth));
                const crop_y = Math.max(0, Math.round((boxTop / 100) * originalMediaHeight));
                
                cropInput.value = `${crop_w}:${crop_h}:${crop_x}:${crop_y}`;
            }

            vcCropBox.addEventListener('mousedown', (e) => {
                if (e.target.classList.contains('vc-handle')) {
                    isResizing = true;
                    currentHandle = e.target.dataset.dir;
                } else {
                    isDragging = true;
                }
                startX = e.clientX;
                startY = e.clientY;
                startBoxLeft = parseFloat(vcCropBox.style.left || 0);
                startBoxTop = parseFloat(vcCropBox.style.top || 0);
                startBoxWidth = parseFloat(vcCropBox.style.width || 100);
                startBoxHeight = parseFloat(vcCropBox.style.height || 100);
            });

            document.addEventListener('mousemove', (e) => {
                if (!isDragging && !isResizing) return;
                const dx = ((e.clientX - startX) / vcContainer.clientWidth) * 100;
                const dy = ((e.clientY - startY) / vcContainer.clientHeight) * 100;

                if (isDragging) {
                    let newLeft = Math.max(0, Math.min(100 - startBoxWidth, startBoxLeft + dx));
                    let newTop = Math.max(0, Math.min(100 - startBoxHeight, startBoxTop + dy));
                    vcCropBox.style.left = newLeft + '%';
                    vcCropBox.style.top = newTop + '%';
                } else if (isResizing) {
                    if (currentHandle.includes('e')) {
                        let newW = Math.max(5, Math.min(100 - startBoxLeft, startBoxWidth + dx));
                        vcCropBox.style.width = newW + '%';
                    }
                    if (currentHandle.includes('s')) {
                        let newH = Math.max(5, Math.min(100 - startBoxTop, startBoxHeight + dy));
                        vcCropBox.style.height = newH + '%';
                    }
                    if (currentHandle.includes('w')) {
                        let maxDx = startBoxWidth - 5;
                        let safeDx = Math.min(maxDx, Math.max(-startBoxLeft, dx));
                        vcCropBox.style.left = (startBoxLeft + safeDx) + '%';
                        vcCropBox.style.width = (startBoxWidth - safeDx) + '%';
                    }
                    if (currentHandle.includes('n')) {
                        let maxDy = startBoxHeight - 5;
                        let safeDy = Math.min(maxDy, Math.max(-startBoxTop, dy));
                        vcCropBox.style.top = (startBoxTop + safeDy) + '%';
                        vcCropBox.style.height = (startBoxHeight - safeDy) + '%';
                    }
                }
                updateCropInput();
            });

            document.addEventListener('mouseup', () => {
                isDragging = false;
                isResizing = false;
            });
        }
    }

    document.addEventListener('mousemove', (e) => {
        if (!isTrimming || mediaDuration === 0) return;
        const rect = vtTrack.getBoundingClientRect();
        let percent = ((e.clientX - rect.left) / rect.width);
        percent = Math.max(0, Math.min(1, percent));
        
        let targetTime = percent * mediaDuration;
        
        if (activeTrimHandle === 'left') {
            currentTrimStart = Math.min(targetTime, currentTrimEnd - 0.5); 
        } else {
            currentTrimEnd = Math.max(targetTime, currentTrimStart + 0.5);
        }
        updateTrimUI();
    });

    document.addEventListener('mouseup', () => { isTrimming = false; });

    optionsContainer.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.stopPropagation();
            optionsContainer.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            optionsContainer.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
            tab.classList.add('active');
            optionsContainer.querySelector(`.${tab.dataset.tab}-tab`).style.display = 'block';
        });
    });

    // Modified Preset Buttons to act as toggles
    optionsContainer.querySelectorAll('.btn-preset').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const tempo = optionsContainer.querySelector('.s-tempo');
            const reverb = optionsContainer.querySelector('.s-reverb');
            const bass = optionsContainer.querySelector('.s-bass');
            
            if (btn.classList.contains('active')) {
                btn.classList.remove('active');
                tempo.value = 1.0; reverb.value = 0; bass.value = 0;
            } else {
                optionsContainer.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const preset = btn.dataset.preset;
                if (preset === 'slowed') {
                    tempo.value = 0.8; reverb.value = 60; bass.value = 5;
                } else if (preset === 'nightcore') {
                    tempo.value = 1.25; reverb.value = 0; bass.value = 0;
                }
            }
            [tempo, reverb, bass].forEach(el => el.dispatchEvent(new Event('input')));
        });
    });

    let currentFilter = "";
    // Modified Style Filters to act as toggles
    optionsContainer.querySelectorAll('.f-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            e.stopPropagation();
            if (chip.classList.contains('active')) {
                chip.classList.remove('active');
                currentFilter = "";
            } else {
                optionsContainer.querySelectorAll('.f-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                currentFilter = chip.dataset.val;
            }
        });
    });

    ['tempo', 'reverb', 'bass'].forEach(cls => {
        const input = optionsContainer.querySelector(`.s-${cls}`);
        const span = input.previousElementSibling.querySelector('.val');
        input.addEventListener('input', (e) => {
            e.stopPropagation();
            span.textContent = input.value;
            optionsContainer.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
        });
    });

    const applyBtn = optionsContainer.querySelector('.btn-apply');
    applyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!currentSelectedFormat) return;
        
        selectEl.value = currentSelectedFormat;
        const hasMediaMods = optionsContainer.querySelector('.media-settings').style.display !== 'none';
        
        if (hasMediaMods) {
            const audioOpts = {
                tempo: parseFloat(optionsContainer.querySelector('.s-tempo').value),
                reverb: parseFloat(optionsContainer.querySelector('.s-reverb').value),
                bass: parseFloat(optionsContainer.querySelector('.s-bass').value),
                trim_start: currentTrimStart > 0 ? formatTrimTime(currentTrimStart) : "",
                trim_end: (currentTrimEnd > 0 && currentTrimEnd < mediaDuration) ? formatTrimTime(currentTrimEnd) : ""
            };
            const videoOpts = {
                resize: optionsContainer.querySelector('.v-resize').value.trim(),
                crop: optionsContainer.querySelector('.v-crop').value.trim(),
                filter: currentFilter,
                trim_start: currentTrimStart > 0 ? formatTrimTime(currentTrimStart) : "",
                trim_end: (currentTrimEnd > 0 && currentTrimEnd < mediaDuration) ? formatTrimTime(currentTrimEnd) : ""
            };
            const custom = optionsContainer.querySelector('.c-flags').value.trim();
            
            selectEl.dataset.audioOpts = JSON.stringify(audioOpts);
            selectEl.dataset.videoOpts = JSON.stringify(videoOpts);
            selectEl.dataset.customFfmpeg = custom;
        } else {
            selectEl.dataset.audioOpts = '';
            selectEl.dataset.videoOpts = '';
            selectEl.dataset.customFfmpeg = '';
        }
        
        const formatText = grid.querySelector('.format-chip.active').textContent.replace('✨', '').trim();
        let modified = false;
        if (hasMediaMods) {
            const a = JSON.parse(selectEl.dataset.audioOpts || "{}");
            const v = JSON.parse(selectEl.dataset.videoOpts || "{}");
            if (a.tempo !== 1.0 || a.reverb !== 0 || a.bass !== 0 || selectEl.dataset.customFfmpeg || v.resize || v.crop || v.filter || v.trim_start || v.trim_end || currentSelectedFormat === origFmt) {
                modified = true;
            }
        }
        
        trigger.querySelector('span').textContent = formatText + (modified ? ' ✨' : '');
        optionsContainer.classList.remove('open');
        trigger.classList.remove('open');
        
        const card = wrapper.closest('.file-card');
        if (card) card.classList.remove('dropdown-open');
        
        selectEl.dispatchEvent(new Event('change'));
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

    updateTabVisibility(currentSelectedFormat || origFmt);
    
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