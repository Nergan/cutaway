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
    trigger.innerHTML = `<span>${selectedOpt && selectedOpt.value ? selectedOpt.text : 'Target format...'}</span><i class="bi bi-chevron-down"></i>`;
    
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'custom-select-options advanced-dropdown';
    
    optionsContainer.innerHTML = `
        <div class="formats-grid"></div>
        <div class="media-settings" style="display: none;">
            <div class="settings-tabs">
                <div class="tab active" data-tab="audio">Audio</div>
                <div class="tab" data-tab="video">Video/Img</div>
                <div class="tab" data-tab="custom">Custom</div>
            </div>
            <div class="tab-content audio-tab active">
                <div class="preset-btns">
                    <button class="btn-preset active" data-preset="none">None</button>
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
                <label>Resize (WxH):</label>
                <input type="text" class="v-resize custom-input" placeholder="e.g. 1920x1080">
                <label>Crop (W:H:X:Y):</label>
                <input type="text" class="v-crop custom-input" placeholder="e.g. 100:100:0:0">
                <label>Style Filter:</label>
                <select class="v-filter custom-input">
                    <option value="">None</option>
                    <option value="grayscale">Grayscale</option>
                    <option value="sepia">Sepia</option>
                    <option value="invert">Invert</option>
                </select>
            </div>
            <div class="tab-content custom-tab" style="display:none;">
                <label>Custom FFmpeg Flags:</label>
                <textarea class="c-flags custom-input" placeholder="-vf scale=320:-1"></textarea>
                <small style="color:var(--danger); display:block; margin-top:5px; line-height:1.2;">No external paths. Flags applied securely before output.</small>
            </div>
        </div>
        <button class="btn-custom btn-apply" style="width: 100%; margin-top: 10px;">APPLY</button>
    `;

    const grid = optionsContainer.querySelector('.formats-grid');
    const mediaFormats = ['mp4','webm','gif','mp3','wav','jpg','png','webp'];
    let currentSelectedFormat = selectEl.value;

    Array.from(selectEl.options).forEach(opt => {
        if (opt.disabled || opt.value === "") return;
        const optDiv = document.createElement('div');
        optDiv.className = 'format-chip' + (currentSelectedFormat === opt.value ? ' active' : '');
        optDiv.textContent = opt.text;
        optDiv.dataset.value = opt.value;
        optDiv.addEventListener('click', (e) => {
            e.stopPropagation();
            grid.querySelectorAll('.format-chip').forEach(c => c.classList.remove('active'));
            optDiv.classList.add('active');
            currentSelectedFormat = opt.value;
            
            const isMedia = mediaFormats.includes(opt.value);
            optionsContainer.querySelector('.media-settings').style.display = isMedia ? 'block' : 'none';
        });
        grid.appendChild(optDiv);
    });

    const isMediaInitial = mediaFormats.includes(currentSelectedFormat);
    optionsContainer.querySelector('.media-settings').style.display = isMediaInitial ? 'block' : 'none';

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
            optionsContainer.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const preset = btn.dataset.preset;
            const tempo = optionsContainer.querySelector('.s-tempo');
            const reverb = optionsContainer.querySelector('.s-reverb');
            const bass = optionsContainer.querySelector('.s-bass');
            if (preset === 'slowed') {
                tempo.value = 0.8; reverb.value = 60; bass.value = 5;
            } else if (preset === 'nightcore') {
                tempo.value = 1.25; reverb.value = 0; bass.value = 0;
            } else {
                tempo.value = 1.0; reverb.value = 0; bass.value = 0;
            }
            [tempo, reverb, bass].forEach(el => el.dispatchEvent(new Event('input')));
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

    optionsContainer.querySelectorAll('input, select, textarea').forEach(el => {
        el.addEventListener('click', e => e.stopPropagation());
        el.addEventListener('mousedown', e => e.stopPropagation());
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
                bass: parseFloat(optionsContainer.querySelector('.s-bass').value)
            };
            const videoOpts = {
                resize: optionsContainer.querySelector('.v-resize').value.trim(),
                crop: optionsContainer.querySelector('.v-crop').value.trim(),
                filter: optionsContainer.querySelector('.v-filter').value
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
        
        const formatText = grid.querySelector('.format-chip.active').textContent;
        let modified = false;
        if (hasMediaMods) {
            const a = JSON.parse(selectEl.dataset.audioOpts || "{}");
            if (a.tempo !== 1.0 || a.reverb !== 0 || a.bass !== 0 || selectEl.dataset.customFfmpeg || JSON.parse(selectEl.dataset.videoOpts || "{}").resize || JSON.parse(selectEl.dataset.videoOpts || "{}").crop || JSON.parse(selectEl.dataset.videoOpts || "{}").filter) {
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