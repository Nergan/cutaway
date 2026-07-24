window.Formular = window.Formular || {};

function formatMediaTime(seconds) {
    if (isNaN(seconds)) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

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
    let selectedMergeId = '';
    
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrapper';
    
    const trigger = document.createElement('div');
    trigger.className = 'custom-select-trigger';
    trigger.innerHTML = `<span>Target format...</span><i class="bi bi-chevron-down"></i>`;
    
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'custom-select-options advanced-dropdown';
    
    optionsContainer.addEventListener('click', e => e.stopPropagation());
    optionsContainer.addEventListener('mousedown', e => e.stopPropagation());

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
                <div class="tab tab-merge" data-tab="merge">Merge</div>
                <div class="tab tab-custom" data-tab="custom">Custom</div>
            </div>
            
            <div class="tab-content audio-tab" style="display:none;">
                <div class="custom-media-player audio-player-ui" style="display:none;">
                    <button class="cmp-play"><i class="bi bi-play-fill"></i></button>
                    <div class="cmp-track"><div class="cmp-progress"></div></div>
                    <div class="cmp-time">0:00 / 0:00</div>
                </div>
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
                    <div class="custom-media-player video-player-ui" style="display:none;">
                        <button class="cmp-play"><i class="bi bi-play-fill"></i></button>
                        <div class="cmp-track"><div class="cmp-progress"></div></div>
                        <div class="cmp-time">0:00 / 0:00</div>
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
            
            <div class="tab-content merge-tab" style="display:none;">
                <label>Target Overwrite / Background Media:</label>
                <div class="merge-files-list"></div>
                <label style="display:flex; align-items:center; gap:8px; margin-top:10px; cursor:pointer;">
                    <input type="checkbox" class="merge-loop" checked style="accent-color: var(--orange); width: 16px; height: 16px;">
                    Loop shorter track to match duration
                </label>
                <small style="color:var(--text-muted); display:block; margin-top:8px;">
                    * Select an uploaded audio/video from the queue to blend into this forge process.
                </small>
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

    function populateMergeDropdown() {
        const mergeList = optionsContainer.querySelector('.merge-files-list');
        mergeList.innerHTML = `<div class="merge-chip ${!selectedMergeId ? 'active' : ''}" data-id="">-- No secondary media selected --</div>`;
        if (!window.Formular.LocalFiles) return;
        
        let candidateCount = 0;
        Object.keys(window.Formular.LocalFiles).forEach(id => {
            if (id === fileId) return; 
            const f = window.Formular.LocalFiles[id];
            
            let isValid = false;
            if (audioOnly.includes(origFmt)) {
                if (f.type.startsWith('video/') || f.type.startsWith('image/')) isValid = true;
            } else {
                if (f.type.startsWith('audio/')) isValid = true;
            }
            
            if (isValid) {
                candidateCount++;
                const isActive = selectedMergeId === id ? 'active' : '';
                mergeList.innerHTML += `<div class="merge-chip ${isActive}" data-id="${id}" title="${f.name}">${f.name}</div>`;
            }
        });

        mergeList.querySelectorAll('.merge-chip').forEach(chip => {
            chip.addEventListener('click', (e) => {
                e.stopPropagation();
                mergeList.querySelectorAll('.merge-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                selectedMergeId = chip.dataset.id;
            });
        });

        return candidateCount;
    }

    function updateTabVisibility(format) {
        const isMedia = mediaFormats.includes(format);
        optionsContainer.querySelector('.media-settings').style.display = isMedia ? 'block' : 'none';
        
        if (isMedia) {
            const tabAudio = optionsContainer.querySelector('.tab-audio');
            const tabVideo = optionsContainer.querySelector('.tab-video');
            const tabMerge = optionsContainer.querySelector('.tab-merge');
            
            const candidates = populateMergeDropdown();
            tabMerge.style.display = candidates > 0 ? 'block' : 'none';

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
        optDiv.className = 'format-chip';
        
        const isOriginal = (opt.value === origFmt);
        optDiv.innerHTML = isOriginal ? `${opt.text} <i class="bi bi-stars" style="color:var(--orange);"></i>` : opt.text;
        
        optDiv.dataset.value = opt.value;
        optDiv.addEventListener('click', (e) => {
            e.stopPropagation();
            grid.querySelectorAll('.format-chip').forEach(c => c.classList.remove('active'));
            optDiv.classList.add('active');
            currentSelectedFormat = opt.value;
            updateTabVisibility(opt.value);
            validateForm();
        });
        grid.appendChild(optDiv);
    });

    // Automatically click original format default enhanced
    if (!currentSelectedFormat) {
        const origChip = Array.from(grid.querySelectorAll('.format-chip')).find(c => c.dataset.value === origFmt);
        if (origChip) origChip.click();
        else if (grid.firstElementChild) grid.firstElementChild.click();
    } else {
        const selChip = Array.from(grid.querySelectorAll('.format-chip')).find(c => c.dataset.value === currentSelectedFormat);
        if (selChip) selChip.click();
    }

    const localFile = window.Formular.LocalFiles ? window.Formular.LocalFiles[fileId] : null;
    let visualCropperActive = false;
    let mediaDuration = 0;
    let currentTrimStart = 0;
    let currentTrimEnd = 0;
    const state = { audioPlayer: null, videoPlayer: null };

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

    function applyFilterPreview(filterVal) {
        const vcMedia = optionsContainer.querySelector('.vc-media');
        if (!vcMedia) return;
        if (filterVal === 'grayscale') vcMedia.style.filter = 'grayscale(100%)';
        else if (filterVal === 'sepia') vcMedia.style.filter = 'sepia(100%)';
        else if (filterVal === 'invert') vcMedia.style.filter = 'invert(100%)';
        else vcMedia.style.filter = 'none';
    }

    function createWebAudioGraph(mediaEl) {
        if (mediaEl._audioNodes) return;
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        
        const ctx = new AudioContext();
        const source = ctx.createMediaElementSource(mediaEl);
        
        const bassFilter = ctx.createBiquadFilter();
        bassFilter.type = "lowshelf";
        bassFilter.frequency.value = 200;
        
        const convolver = ctx.createConvolver();
        const rate = ctx.sampleRate;
        const len = rate * 2.5; 
        const impulse = ctx.createBuffer(2, len, rate);
        for (let i = 0; i < len; i++) {
            const d = Math.exp(-i / (rate * 0.5));
            impulse.getChannelData(0)[i] = (Math.random() * 2 - 1) * d;
            impulse.getChannelData(1)[i] = (Math.random() * 2 - 1) * d;
        }
        convolver.buffer = impulse;
        
        const dry = ctx.createGain();
        const wet = ctx.createGain();
        dry.gain.value = 1;
        wet.gain.value = 0;
        
        source.connect(bassFilter);
        bassFilter.connect(dry);
        dry.connect(ctx.destination);
        
        bassFilter.connect(convolver);
        convolver.connect(wet);
        wet.connect(ctx.destination);
        
        mediaEl._audioNodes = { ctx, bassFilter, dry, wet };
    }

    function syncLiveAudioFX() {
        const tempo = parseFloat(optionsContainer.querySelector('.s-tempo').value) || 1.0;
        const reverb = parseFloat(optionsContainer.querySelector('.s-reverb').value) || 0;
        const bass = parseFloat(optionsContainer.querySelector('.s-bass').value) || 0;
        
        [state.audioPlayer, state.videoPlayer].forEach(el => {
            if (!el) return;
            el.playbackRate = tempo;
            if (el._audioNodes) {
                el._audioNodes.bassFilter.gain.value = bass;
                const wetVal = reverb / 100;
                el._audioNodes.wet.gain.value = wetVal;
                el._audioNodes.dry.gain.value = 1 - (wetVal * 0.5);
            }
        });
    }

    function initCustomPlayer(uiContainer, mediaEl) {
        uiContainer.style.display = 'flex';
        const playBtn = uiContainer.querySelector('.cmp-play');
        const track = uiContainer.querySelector('.cmp-track');
        const progress = uiContainer.querySelector('.cmp-progress');
        const timeDisp = uiContainer.querySelector('.cmp-time');
        
        playBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (mediaEl.paused) {
                if (state.audioPlayer && state.audioPlayer !== mediaEl) { state.audioPlayer.pause(); }
                if (state.videoPlayer && state.videoPlayer !== mediaEl) { state.videoPlayer.pause(); }
                mediaEl.play();
            } else {
                mediaEl.pause();
            }
        });
        
        const card = wrapper.closest('.file-card');

        mediaEl.addEventListener('play', () => {
            playBtn.innerHTML = '<i class="bi bi-pause-fill"></i>';
            if (card) card.classList.add('is-playing');
            createWebAudioGraph(mediaEl);
            if (mediaEl._audioNodes && mediaEl._audioNodes.ctx.state === 'suspended') {
                mediaEl._audioNodes.ctx.resume();
            }
            syncLiveAudioFX();
        });

        mediaEl.addEventListener('pause', () => {
            playBtn.innerHTML = '<i class="bi bi-play-fill"></i>';
            if (card) card.classList.remove('is-playing');
        });

        mediaEl.addEventListener('ended', () => {
            playBtn.innerHTML = '<i class="bi bi-play-fill"></i>';
            if (card) card.classList.remove('is-playing');
        });
        
        mediaEl.addEventListener('timeupdate', () => {
            if (!mediaEl.duration) return;
            const pct = (mediaEl.currentTime / mediaEl.duration) * 100;
            progress.style.width = `${pct}%`;
            timeDisp.textContent = `${formatMediaTime(mediaEl.currentTime)} / ${formatMediaTime(mediaEl.duration)}`;
            
            if (mediaDuration > 0 && (mediaEl.currentTime < currentTrimStart || mediaEl.currentTime > currentTrimEnd)) {
                mediaEl.currentTime = currentTrimStart;
            }
        });
        
        let isScrubbing = false;
        const updatePlayhead = (e) => {
            const rect = track.getBoundingClientRect();
            let pct = (e.clientX - rect.left) / rect.width;
            pct = Math.max(0, Math.min(1, pct));
            mediaEl.currentTime = pct * mediaEl.duration;
        };

        track.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            isScrubbing = true;
            updatePlayhead(e);
        });

        document.addEventListener('mousemove', (e) => {
            if (isScrubbing) updatePlayhead(e);
        });

        document.addEventListener('mouseup', () => {
            isScrubbing = false;
        });
    }

    if (localFile) {
        const localFileUrl = URL.createObjectURL(localFile);
        
        if (localFile.type.startsWith('audio/') || audioOnly.includes(origFmt)) {
            const audioEl = document.createElement('audio');
            audioEl.src = localFileUrl;
            audioEl.crossOrigin = "anonymous";
            state.audioPlayer = audioEl;
            
            audioEl.onloadedmetadata = () => {
                mediaDuration = audioEl.duration;
                currentTrimEnd = mediaDuration;
                updateTrimUI();
                initCustomPlayer(optionsContainer.querySelector('.audio-player-ui'), audioEl);
            };
            vtWrapper.style.display = 'block';
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
                mediaEl.className = 'vc-media';
                mediaEl.src = localFileUrl;
                mediaEl.playsInline = true;
                mediaEl.crossOrigin = "anonymous";
                state.videoPlayer = mediaEl;
                
                mediaEl.onloadedmetadata = () => {
                    originalMediaWidth = mediaEl.videoWidth;
                    originalMediaHeight = mediaEl.videoHeight;
                    visualCropperActive = true;
                    mediaDuration = mediaEl.duration;
                    currentTrimEnd = mediaDuration;
                    updateTrimUI();
                    vtWrapper.style.display = 'block';
                    initCustomPlayer(optionsContainer.querySelector('.video-player-ui'), mediaEl);
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

            let isDragging = false, isResizing = false;
            let currentHandle = null, startX, startY, startBoxLeft, startBoxTop, startBoxWidth, startBoxHeight;
            
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
                validateForm();
            }

            vcCropBox.addEventListener('mousedown', (e) => {
                if (e.target.classList.contains('vc-handle')) {
                    isResizing = true; currentHandle = e.target.dataset.dir;
                } else { isDragging = true; }
                startX = e.clientX; startY = e.clientY;
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
                    vcCropBox.style.left = newLeft + '%'; vcCropBox.style.top = newTop + '%';
                } else if (isResizing) {
                    if (currentHandle.includes('e')) { vcCropBox.style.width = Math.max(5, Math.min(100 - startBoxLeft, startBoxWidth + dx)) + '%'; }
                    if (currentHandle.includes('s')) { vcCropBox.style.height = Math.max(5, Math.min(100 - startBoxTop, startBoxHeight + dy)) + '%'; }
                    if (currentHandle.includes('w')) {
                        let safeDx = Math.min(startBoxWidth - 5, Math.max(-startBoxLeft, dx));
                        vcCropBox.style.left = (startBoxLeft + safeDx) + '%'; vcCropBox.style.width = (startBoxWidth - safeDx) + '%';
                    }
                    if (currentHandle.includes('n')) {
                        let safeDy = Math.min(startBoxHeight - 5, Math.max(-startBoxTop, dy));
                        vcCropBox.style.top = (startBoxTop + safeDy) + '%'; vcCropBox.style.height = (startBoxHeight - safeDy) + '%';
                    }
                }
                updateCropInput();
            });

            document.addEventListener('mouseup', () => { isDragging = false; isResizing = false; });
        }
    }

    document.addEventListener('mousemove', (e) => {
        if (!isTrimming || mediaDuration === 0) return;
        const rect = vtTrack.getBoundingClientRect();
        let percent = ((e.clientX - rect.left) / rect.width);
        percent = Math.max(0, Math.min(1, percent));
        
        let targetTime = percent * mediaDuration;
        if (activeTrimHandle === 'left') currentTrimStart = Math.min(targetTime, currentTrimEnd - 0.5); 
        else currentTrimEnd = Math.max(targetTime, currentTrimStart + 0.5);
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
                if (preset === 'slowed') { tempo.value = 0.8; reverb.value = 60; bass.value = 5; } 
                else if (preset === 'nightcore') { tempo.value = 1.25; reverb.value = 0; bass.value = 0; }
            }
            [tempo, reverb, bass].forEach(el => el.dispatchEvent(new Event('input')));
        });
    });

    let currentFilter = "";
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
            applyFilterPreview(currentFilter);
        });
    });

    ['tempo', 'reverb', 'bass'].forEach(cls => {
        const input = optionsContainer.querySelector(`.s-${cls}`);
        const span = input.previousElementSibling.querySelector('.val');
        input.addEventListener('input', (e) => {
            e.stopPropagation();
            span.textContent = input.value;
            optionsContainer.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
            syncLiveAudioFX();
        });
    });

    const applyBtn = optionsContainer.querySelector('.btn-apply');
    const convertBtnMain = wrapper.closest('.file-card').querySelector('.btn-custom:not(.btn-remove)');

    function validateForm() {
        let valid = true;
        const flags = optionsContainer.querySelector('.c-flags').value;
        if (/(\s|^)-(i|f|d|y|n)(\s|$)|(\.\.)|(\/)|(\\)/.test(flags)) valid = false;

        const crop = optionsContainer.querySelector('.v-crop').value.trim();
        if (crop && !/^\d+:\d+:\d+:\d+$/.test(crop)) valid = false;

        const resize = optionsContainer.querySelector('.v-resize').value.trim();
        if (resize && !/^\d+x\d+$/i.test(resize)) valid = false;

        if (!currentSelectedFormat) valid = false;

        applyBtn.disabled = !valid;
        if (convertBtnMain) convertBtnMain.disabled = !valid;

        if (!valid) {
            applyBtn.innerText = "INVALID PARAMS";
            applyBtn.style.background = "var(--danger)";
        } else {
            applyBtn.innerText = "APPLY";
            applyBtn.style.background = "var(--orange)";
        }
    }

    ['input', 'change'].forEach(evt => {
        optionsContainer.addEventListener(evt, validateForm);
    });

    applyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!currentSelectedFormat || applyBtn.disabled) return;
        
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
            
            selectEl.dataset.audioOpts = JSON.stringify(audioOpts);
            selectEl.dataset.videoOpts = JSON.stringify(videoOpts);
            selectEl.dataset.customFfmpeg = optionsContainer.querySelector('.c-flags').value.trim();
            selectEl.dataset.mergeId = selectedMergeId;
            selectEl.dataset.mergeLoop = optionsContainer.querySelector('.merge-loop').checked;
        } else {
            selectEl.dataset.audioOpts = '';
            selectEl.dataset.videoOpts = '';
            selectEl.dataset.customFfmpeg = '';
            selectEl.dataset.mergeId = '';
            selectEl.dataset.mergeLoop = false;
        }
        
        const formatText = grid.querySelector('.format-chip.active').textContent.replace('✨', '').trim();
        let modified = false;
        if (hasMediaMods) {
            const a = JSON.parse(selectEl.dataset.audioOpts || "{}");
            const v = JSON.parse(selectEl.dataset.videoOpts || "{}");
            if (a.tempo !== 1.0 || a.reverb !== 0 || a.bass !== 0 || selectEl.dataset.customFfmpeg || v.resize || v.crop || v.filter || v.trim_start || v.trim_end || selectEl.dataset.mergeId || currentSelectedFormat === origFmt) {
                modified = true;
            }
        }
        
        trigger.querySelector('span').textContent = formatText + (modified ? ' ✨' : '');
        optionsContainer.classList.remove('open');
        trigger.classList.remove('open');
        
        if (state.audioPlayer) state.audioPlayer.pause();
        if (state.videoPlayer) state.videoPlayer.pause();
        
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
        
        if (optionsContainer.classList.contains('open')) {
            if (state.audioPlayer) state.audioPlayer.pause();
            if (state.videoPlayer) state.videoPlayer.pause();
            optionsContainer.classList.remove('open');
            trigger.classList.remove('open');
            populateMergeDropdown();
        } else {
            optionsContainer.classList.add('open');
            trigger.classList.add('open');
            validateForm();
        }
        
        const card = wrapper.closest('.file-card');
        if (card) card.classList.toggle('dropdown-open');
    });

    updateTabVisibility(currentSelectedFormat || origFmt);
    wrapper.appendChild(trigger);
    wrapper.appendChild(optionsContainer);
    selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
};

document.addEventListener('click', (e) => {
    document.querySelectorAll('.custom-select-options.open').forEach(el => {
        const wrapper = el.closest('.custom-select-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
            el.classList.remove('open');
            if (el.previousElementSibling) el.previousElementSibling.classList.remove('open');
            const card = el.closest('.file-card');
            if (card) card.classList.remove('dropdown-open');
            
            const p = wrapper.querySelector('.audio-player-ui');
            const pv = wrapper.querySelector('.video-player-ui');
            if (p && p._audioRef) p._audioRef.pause();
            if (pv && pv._videoRef) pv._videoRef.pause();
        }
    });
});