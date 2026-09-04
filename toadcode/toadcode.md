Вот исправления, которые гарантированно устранят проблему блокировки сайдбара и сделают кнопку 'Code' яркой и гармоничной в интерфейсе.

Для полного решения проблемы с растягиванием родительских flex-контейнеров (Blowout effect) мы зададим им базовую ширину 0 (оставляя ответственность за размеры правилу `flex-grow-1`) и добавим строгие правила переноса строк в Markdown.

### [*] 1. static\styles\base.css

Добавим правило `width: 0;`, которое заставит `.editor-section` игнорировать ширину контента и опираться только на распределение свободного места:

```search
.editor-section {
    min-width: 0;
    min-height: 0; /* Critical fix for flexbox scrolling inside the editor */
}
```

```replace
.editor-section {
    min-width: 0;
    min-height: 0; /* Critical fix for flexbox scrolling inside the editor */
    width: 0; /* Prevents flex blowout from wide content in Markdown/HTML */
}
```

### [*] 2. toadcode.html

Восстановим класс `w-100` для дочерних контейнеров и добавим `overflow-wrap: anywhere`, чтобы очень длинные неразрывные строки (например, ссылки) в Markdown без проблем переносились:

```search
                <div id="editorContainer" class="flex-grow-1 d-none z-1 position-relative" style="min-width: 0; min-height: 0;">
                    <textarea id="codeInput" class="code-editor w-100 h-100" spellcheck="false" {% if code_id %}readonly{% endif %}></textarea>
                </div>
                
                <div id="mdPreview" class="flex-grow-1 d-none z-2 overflow-auto p-4 custom-font" style="min-width: 0; min-height: 0; background: rgba(0,0,0,0.25); color: white; word-wrap: break-word;"></div>
                <iframe id="htmlPreview" class="flex-grow-1 d-none z-2 border-0" sandbox="allow-scripts" style="min-width: 0; min-height: 0; background: rgba(255,255,255,0.9);"></iframe>
```

```replace
                <div id="editorContainer" class="flex-grow-1 w-100 d-none z-1 position-relative" style="min-width: 0; min-height: 0;">
                    <textarea id="codeInput" class="code-editor w-100 h-100" spellcheck="false" {% if code_id %}readonly{% endif %}></textarea>
                </div>
                
                <div id="mdPreview" class="flex-grow-1 w-100 d-none z-2 overflow-auto p-4 custom-font" style="min-width: 0; min-height: 0; background: rgba(0,0,0,0.25); color: white; word-wrap: break-word; overflow-wrap: anywhere;"></div>
                <iframe id="htmlPreview" class="flex-grow-1 w-100 d-none z-2 border-0" sandbox="allow-scripts" style="min-width: 0; min-height: 0; background: rgba(255,255,255,0.9);"></iframe>
```

### [*] 3. static\styles\buttons.css

Добавим новый класс для яркого неонового цвета кнопки:

```search
.copy-code-btn.error {
    background: rgba(220, 53, 69, 0.2);
    border-color: rgba(220, 53, 69, 0.4);
    color: #dc3545;
}
```

```replace
.copy-code-btn.error {
    background: rgba(220, 53, 69, 0.2);
    border-color: rgba(220, 53, 69, 0.4);
    color: #dc3545;
}

.btn-code-mode {
    color: lime !important;
    border-color: lime !important;
    text-shadow: 0 0 5px rgba(0, 255, 0, 0.4);
    background: rgba(0, 255, 0, 0.1) !important;
}
```

### [*] 4. scripts\vfs.js

Заменим тусклый цвет `text-success` от Bootstrap на наш новый кастомный яркий класс в логике работы кнопки:

```search
            if (isPreviewMode) {
                ui.previewBtn.innerHTML = '<i class="bi bi-code-slash"></i> Code';
                ui.previewBtn.classList.add('text-success');
                renderPreview(file);
            } else {
                ui.previewBtn.innerHTML = '<i class="bi bi-eye"></i> Preview';
                ui.previewBtn.classList.remove('text-success');
                hidePreview();
            }
```

```replace
            if (isPreviewMode) {
                ui.previewBtn.innerHTML = '<i class="bi bi-code-slash"></i> Code';
                ui.previewBtn.classList.add('btn-code-mode');
                renderPreview(file);
            } else {
                ui.previewBtn.innerHTML = '<i class="bi bi-eye"></i> Preview';
                ui.previewBtn.classList.remove('btn-code-mode');
                hidePreview();
            }
```

```search
            const fileType = getFileTypeByContent(file.path, file.content);
            if (fileType) {
                ui.previewBtn.classList.remove('d-none');
                if (isPreviewMode) {
                    renderPreview(file, fileType);
                } else {
                    ui.editorContainer.classList.remove('d-none');
                    hidePreview();
                }
            } else {
                ui.previewBtn.classList.add('d-none');
                isPreviewMode = false;
                ui.previewBtn.innerHTML = '<i class="bi bi-eye"></i> Preview';
                ui.previewBtn.classList.remove('text-success');
                ui.editorContainer.classList.remove('d-none');
                hidePreview();
            }
```

```replace
            const fileType = getFileTypeByContent(file.path, file.content);
            if (fileType) {
                ui.previewBtn.classList.remove('d-none');
                if (isPreviewMode) {
                    renderPreview(file, fileType);
                } else {
                    ui.editorContainer.classList.remove('d-none');
                    hidePreview();
                }
            } else {
                ui.previewBtn.classList.add('d-none');
                isPreviewMode = false;
                ui.previewBtn.innerHTML = '<i class="bi bi-eye"></i> Preview';
                ui.previewBtn.classList.remove('btn-code-mode');
                ui.editorContainer.classList.remove('d-none');
                hidePreview();
            }
```
