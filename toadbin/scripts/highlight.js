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

    // Инициализация: применяем подсветку только к заблокированным полям
    function init() {
        document.querySelectorAll('.code-editor').forEach(textarea => {
            // Если поле уже обработано – пропускаем
            if (textarea.dataset.hljsProcessed === 'true') return;

            // Применяем подсветку только для disabled (режим чтения)
            if (textarea.disabled) {
                setupReadOnly(textarea);
            }
            // Для редактируемых полей ничего не делаем — они остаются обычными textarea
        });
    }

    // Режим только для чтения (code_id присутствует)
    function setupReadOnly(textarea) {
        // Помечаем как обработанное
        textarea.dataset.hljsProcessed = 'true';

        // Сохраняем текущую прокрутку (на всякий случай, хотя в read-only она не критична)
        const oldScrollTop = textarea.scrollTop;

        // Создаём обёртку и перемещаем в неё textarea
        const wrapper = document.createElement('div');
        wrapper.className = 'code-editor-wrapper';
        wrapper.style.position = 'relative'; // для возможных будущих нужд
        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(textarea);

        // Восстанавливаем прокрутку (если вдруг сбросилась)
        textarea.scrollTop = oldScrollTop;

        // Скрываем текстовое поле
        textarea.style.display = 'none';

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
    }

    // Запуск
    loadTheme();
    loadHighlightJs(init);
})();