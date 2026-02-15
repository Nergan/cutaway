(function() {
    'use strict';

    function loadTheme() {
        if (!document.querySelector('link[href*="highlight.js/11.8.0/styles/github-dark.min.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css';
            document.head.appendChild(link);
        }
    }

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

                const lang = languages[loaded++];
                const langScript = document.createElement('script');
                langScript.src = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/${lang}.min.js`;
                langScript.onload = loadNext;
                langScript.onerror = loadNext;
                document.head.appendChild(langScript);
            }

            loadNext();
        };

        document.head.appendChild(script);
    }

    function init() {
        document.querySelectorAll('.code-editor').forEach(setupTextarea);
    }

    function setupTextarea(textarea) {
        if (textarea.dataset.hljsProcessed === 'true') return;
        textarea.dataset.hljsProcessed = 'true';

        const isReadOnly = textarea.disabled;

        const wrapper = document.createElement('div');
        wrapper.className = 'code-editor-wrapper';
        wrapper.style.position = 'relative';
        wrapper.style.width = textarea.offsetWidth ? textarea.offsetWidth + 'px' : '100%';
        wrapper.style.height = textarea.offsetHeight ? textarea.offsetHeight + 'px' : '100%';

        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(textarea);

        textarea.style.width = '100%';
        textarea.style.height = '100%';
        textarea.style.display = '';

        if (isReadOnly) {
            setupReadOnly(textarea, wrapper);
        } else {
            setupEditable(textarea, wrapper);
        }
    }

    // ------------------------
    // READ ONLY MODE
    // ------------------------
    function setupReadOnly(textarea, wrapper) {
        textarea.style.display = 'none';

        const pre = document.createElement('pre');
        pre.className = 'hljs';
        pre.style.margin = '0';
        pre.style.width = '100%';
        pre.style.overflow = 'auto';
        pre.style.whiteSpace = 'pre-wrap';
        pre.style.wordWrap = 'break-word';

        const codeElement = document.createElement('code');
        codeElement.textContent = textarea.value || '';
        pre.appendChild(codeElement);

        const style = window.getComputedStyle(textarea);
        pre.style.padding = style.padding;
        pre.style.border = style.border;
        pre.style.fontFamily = style.fontFamily;
        pre.style.fontSize = style.fontSize;
        pre.style.lineHeight = style.lineHeight;
        pre.style.boxSizing = style.boxSizing;

        wrapper.appendChild(pre);

        hljs.highlightElement(codeElement);
    }

    // ------------------------
    // EDIT MODE
    // ------------------------
    function setupEditable(textarea, wrapper) {
        const pre = document.createElement('pre');
        pre.className = 'hljs';

        pre.style.position = 'absolute';
        pre.style.top = '0';
        pre.style.left = '0';
        pre.style.right = '0';
        pre.style.bottom = '0';
        pre.style.margin = '0';
        pre.style.background = 'transparent';
        pre.style.pointerEvents = 'none';
        pre.style.overflow = 'hidden'; // FIX: убираем собственный скролл
        pre.style.whiteSpace = 'pre-wrap';
        pre.style.wordWrap = 'break-word';

        const style = window.getComputedStyle(textarea);
        pre.style.fontFamily = style.fontFamily;
        pre.style.fontSize = style.fontSize;
        pre.style.lineHeight = style.lineHeight;
        pre.style.padding = style.padding;
        pre.style.boxSizing = style.boxSizing;

        const codeElement = document.createElement('code');
        codeElement.style.background = 'transparent';
        pre.appendChild(codeElement);
        wrapper.appendChild(pre);

        textarea.style.background = 'transparent';
        textarea.style.color = 'transparent';
        textarea.style.caretColor = '#ffffff';
        textarea.style.position = 'relative';
        textarea.style.zIndex = '1';
        textarea.style.resize = 'none';

        function updateHighlight() {
            const code = textarea.value;

            if (!code) {
                codeElement.textContent = '';
                return;
            }

            const result = hljs.highlightAuto(code);
            codeElement.className = result.language ? `language-${result.language}` : '';
            codeElement.innerHTML = result.value;
        }

        function syncScroll() {
            requestAnimationFrame(() => {
                pre.scrollTop = textarea.scrollTop;
                pre.scrollLeft = textarea.scrollLeft;
            });
        }

        updateHighlight();

        textarea.addEventListener('input', updateHighlight);
        textarea.addEventListener('scroll', syncScroll);
    }

    loadTheme();
    loadHighlightJs(init);

})();
