(function() {
    'use strict';

    // Стили для скрытия скроллбара у pre в режиме редактирования (если понадобятся)
    const style = document.createElement('style');
    style.textContent = `
        .hljs-editable {
            scrollbar-width: none;
            -ms-overflow-style: none;
        }
        .hljs-editable::-webkit-scrollbar {
            display: none;
        }
    `;
    document.head.appendChild(style);

    // Загружаем тему highlight.js
    function loadTheme() {
        if (!document.querySelector('link[href*="highlight.js/11.8.0/styles/github-dark.min.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css';
            document.head.appendChild(link);
        }
    }

    // Загружаем основной скрипт и дополнительные языки
    function loadHighlightJs(callback) {
        if (typeof hljs !== 'undefined') {
            callback();
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js';
        script.onload = function() {
            const languages = ['python', 'javascript', 'java', 'cpp', 'php', 'html', 'css', 'sql', 'bash'];
            let loaded = 0;
            function loadNext() {
                if (loaded >= languages.length) {
                    callback();
                    return;
                }
                const lang = languages[loaded];
                const langScript = document.createElement('script');
                langScript.src = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/${lang}.min.js`;
                langScript.onload = loadNext;
                langScript.onerror = loadNext;
                document.head.appendChild(langScript);
                loaded++;
            }
            loadNext();
        };
        document.head.appendChild(script);
    }

    // Инициализация всех текстовых полей
    function init() {
        document.querySelectorAll('.code-editor').forEach(setupTextarea);
    }

    function setupTextarea(textarea) {
        if (textarea.dataset.hljsProcessed === 'true') return;
        textarea.dataset.hljsProcessed = 'true';

        const isReadOnly = textarea.disabled;

        // Создаём обёртку
        let wrapper = document.createElement('div');
        wrapper.className = 'code-editor-wrapper';
        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(textarea);

        // Сбрасываем стили
        textarea.style.width = '100%';
        textarea.style.height = '100%';
        textarea.style.display = '';

        if (isReadOnly) {
            setupReadOnly(textarea, wrapper);
        } else {
            setupEditable(textarea, wrapper);
        }
    }

    // Режим только для чтения (с подсветкой)
    function setupReadOnly(textarea, wrapper) {
        textarea.style.display = 'none';

        const code = textarea.value;

        const pre = document.createElement('pre');
        pre.className = 'hljs hljs-readonly';
        const codeElement = document.createElement('code');
        codeElement.textContent = code; // исходный текст
        pre.appendChild(codeElement);

        // Копируем стили из textarea
        const style = window.getComputedStyle(textarea);
        pre.style.margin = '0';
        pre.style.padding = style.padding;
        pre.style.border = style.border;
        pre.style.fontFamily = style.fontFamily;
        pre.style.fontSize = style.fontSize;
        pre.style.lineHeight = style.lineHeight;
        pre.style.boxSizing = style.boxSizing;
        pre.style.width = '100%';
        pre.style.height = '100%';
        pre.style.overflow = 'auto';
        pre.style.whiteSpace = 'pre-wrap';
        pre.style.wordWrap = 'break-word';

        wrapper.appendChild(pre);

        // Подсветка с ожиданием загрузки hljs
        function applyHighlight() {
            if (typeof hljs !== 'undefined') {
                hljs.highlightElement(codeElement);
            } else {
                setTimeout(applyHighlight, 50);
            }
        }
        applyHighlight();
    }

    // Режим редактирования (с прокруткой через transform)
    function setupEditable(textarea, wrapper) {
        // Контейнер для подсвеченного кода (без собственной прокрутки)
        const highlightDiv = document.createElement('div');
        highlightDiv.className = 'hljs';
        highlightDiv.style.position = 'absolute';
        highlightDiv.style.top = '0';
        highlightDiv.style.left = '0';
        highlightDiv.style.right = '0';
        highlightDiv.style.bottom = '0';
        highlightDiv.style.margin = '0';
        highlightDiv.style.padding = '0';
        highlightDiv.style.border = 'none';
        highlightDiv.style.background = 'transparent';
        highlightDiv.style.pointerEvents = 'none';
        highlightDiv.style.overflow = 'hidden';
        highlightDiv.style.whiteSpace = 'pre-wrap';
        highlightDiv.style.wordWrap = 'break-word';

        // Копируем стили текста из textarea
        const style = window.getComputedStyle(textarea);
        highlightDiv.style.fontFamily = style.fontFamily;
        highlightDiv.style.fontSize = style.fontSize;
        highlightDiv.style.lineHeight = style.lineHeight;
        highlightDiv.style.paddingTop = style.paddingTop;
        highlightDiv.style.paddingRight = style.paddingRight;
        highlightDiv.style.paddingBottom = style.paddingBottom;
        highlightDiv.style.paddingLeft = style.paddingLeft;
        highlightDiv.style.borderTopWidth = style.borderTopWidth;
        highlightDiv.style.borderRightWidth = style.borderRightWidth;
        highlightDiv.style.borderBottomWidth = style.borderBottomWidth;
        highlightDiv.style.borderLeftWidth = style.borderLeftWidth;
        highlightDiv.style.borderTopStyle = 'solid';
        highlightDiv.style.borderRightStyle = 'solid';
        highlightDiv.style.borderBottomStyle = 'solid';
        highlightDiv.style.borderLeftStyle = 'solid';
        highlightDiv.style.borderTopColor = 'transparent';
        highlightDiv.style.borderRightColor = 'transparent';
        highlightDiv.style.borderBottomColor = 'transparent';
        highlightDiv.style.borderLeftColor = 'transparent';
        highlightDiv.style.boxSizing = style.boxSizing;

        const codeElement = document.createElement('code');
        codeElement.style.background = 'transparent';
        highlightDiv.appendChild(codeElement);
        wrapper.appendChild(highlightDiv);

        // Настройка textarea
        textarea.style.background = 'transparent';
        textarea.style.color = 'transparent';
        textarea.style.caretColor = 'white';
        textarea.style.position = 'relative';
        textarea.style.zIndex = '1';
        textarea.style.backgroundColor = 'transparent';

        // Обновление подсветки
        function updateHighlight() {
            const code = textarea.value;
            const result = hljs.highlightAuto(code);
            codeElement.className = result.language ? `language-${result.language}` : '';
            codeElement.innerHTML = result.value;
            highlightDiv.style.height = textarea.scrollHeight + 'px';
        }

        // Синхронизация прокрутки
        function syncScroll() {
            highlightDiv.style.transform = `translateY(-${textarea.scrollTop}px)`;
        }

        updateHighlight();
        highlightDiv.style.height = textarea.scrollHeight + 'px';

        textarea.addEventListener('input', updateHighlight);
        textarea.addEventListener('scroll', syncScroll);

        // Обновление высоты при изменении размеров
        if (window.ResizeObserver) {
            const resizeObserver = new ResizeObserver(() => {
                highlightDiv.style.height = textarea.scrollHeight + 'px';
            });
            resizeObserver.observe(textarea);
        } else {
            window.addEventListener('resize', () => {
                highlightDiv.style.height = textarea.scrollHeight + 'px';
            });
        }
    }

    // Запуск
    loadTheme();
    loadHighlightJs(init);
})();