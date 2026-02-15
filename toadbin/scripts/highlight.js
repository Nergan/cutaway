(function() {
    'use strict';

    // Загружаем тему highlight.js, если ещё не загружена
    function loadTheme() {
        if (!document.querySelector('link[href*="highlight.js/11.8.0/styles/github-dark.min.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css';
            document.head.appendChild(link);
        }
    }

    // Загружаем основной скрипт highlight.js и дополнительные языки
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

        // Создаём общую обёртку для всех режимов
        let wrapper = document.createElement('div');
        wrapper.className = 'code-editor-wrapper';
        wrapper.style.position = 'relative';

        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(textarea);

        // !!! ИСПРАВЛЕНИЕ: сохраняем исходные размеры textarea и применяем их к wrapper,
        // чтобы предотвратить схлопывание при скрытии или изменении стилей.
        const originalWidth = textarea.offsetWidth;
        const originalHeight = textarea.offsetHeight;
        if (originalWidth > 0) wrapper.style.width = originalWidth + 'px';
        if (originalHeight > 0) wrapper.style.height = originalHeight + 'px';

        // Больше не принудительно задаём width/height: 100% для textarea,
        // оставляем исходные размеры, чтобы не ломать скроллбары.
        // textarea.style.width = '100%';   // <-- удалено
        // textarea.style.height = '100%';  // <-- удалено

        if (isReadOnly) {
            setupReadOnly(textarea, wrapper);
        } else {
            setupEditable(textarea, wrapper);
        }
    }

    // Режим только для чтения (code_id)
    function setupReadOnly(textarea, wrapper) {
        // Сначала получаем код и создаём pre
        const code = textarea.value;
        const result = hljs.highlightAuto(code);

        const pre = document.createElement('pre');
        pre.className = 'hljs';
        const codeElement = document.createElement('code');
        codeElement.className = result.language ? `language-${result.language}` : '';
        codeElement.innerHTML = result.value;
        codeElement.style.background = 'transparent';
        pre.appendChild(codeElement);

        // Копируем стили из textarea для совпадения размеров и отступов
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

        // Скрываем текстовое поле только после того, как pre уже добавлен,
        // чтобы wrapper не схлопнулся (размеры wrapper уже зафиксированы)
        textarea.style.display = 'none';
    }

    // Режим редактирования (главная страница)
    function setupEditable(textarea, wrapper) {
        // Запрещаем ручное изменение размера, чтобы не сломать синхронизацию
        textarea.style.resize = 'none';

        // Создаём pre для подсветки
        const pre = document.createElement('pre');
        pre.className = 'hljs';
        pre.style.position = 'absolute';
        pre.style.top = '0';
        pre.style.left = '0';
        pre.style.right = '0';
        pre.style.bottom = '0';
        pre.style.margin = '0';
        pre.style.padding = '0';
        pre.style.border = 'none';
        pre.style.background = 'transparent';
        pre.style.pointerEvents = 'none';
        pre.style.overflow = 'auto';
        pre.style.whiteSpace = 'pre-wrap';
        pre.style.wordWrap = 'break-word';

        // Копируем стили из textarea для точного совпадения текста
        const style = window.getComputedStyle(textarea);
        pre.style.fontFamily = style.fontFamily;
        pre.style.fontSize = style.fontSize;
        pre.style.lineHeight = style.lineHeight;
        pre.style.paddingTop = style.paddingTop;
        pre.style.paddingRight = style.paddingRight;
        pre.style.paddingBottom = style.paddingBottom;
        pre.style.paddingLeft = style.paddingLeft;
        // Копируем толщину границы (делаем прозрачной)
        pre.style.borderTopWidth = style.borderTopWidth;
        pre.style.borderRightWidth = style.borderRightWidth;
        pre.style.borderBottomWidth = style.borderBottomWidth;
        pre.style.borderLeftWidth = style.borderLeftWidth;
        pre.style.borderTopStyle = 'solid';
        pre.style.borderRightStyle = 'solid';
        pre.style.borderBottomStyle = 'solid';
        pre.style.borderLeftStyle = 'solid';
        pre.style.borderTopColor = 'transparent';
        pre.style.borderRightColor = 'transparent';
        pre.style.borderBottomColor = 'transparent';
        pre.style.borderLeftColor = 'transparent';
        pre.style.boxSizing = style.boxSizing;

        const codeElement = document.createElement('code');
        codeElement.style.background = 'transparent';
        pre.appendChild(codeElement);
        wrapper.appendChild(pre);

        // Настраиваем текстовое поле
        textarea.style.background = 'transparent';
        textarea.style.color = 'transparent';
        textarea.style.caretColor = 'white';
        textarea.style.position = 'relative';
        textarea.style.zIndex = '1';
        textarea.style.backgroundColor = 'transparent';

        // Функция обновления подсветки
        function updateHighlight() {
            const code = textarea.value;
            const result = hljs.highlightAuto(code);
            codeElement.className = result.language ? `language-${result.language}` : '';
            codeElement.innerHTML = result.value;
        }

        // Синхронизация прокрутки
        function syncScroll() {
            pre.scrollTop = textarea.scrollTop;
            pre.scrollLeft = textarea.scrollLeft;
        }

        updateHighlight();
        textarea.addEventListener('input', updateHighlight);
        textarea.addEventListener('scroll', syncScroll);
    }

    // Запуск
    loadTheme();
    loadHighlightJs(init);
})();