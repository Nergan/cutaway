(function() {
    'use strict';

    const EXT_LANG = {
        json: 'json',
        js: 'javascript',
        mjs: 'javascript',
        cjs: 'javascript',
        ts: 'typescript',
        py: 'python',
        html: 'xml',
        htm: 'xml',
        css: 'css',
        md: 'markdown',
        yml: 'yaml',
        yaml: 'yaml',
        xml: 'xml',
        sh: 'bash',
        bash: 'bash',
        c: 'c',
        h: 'c',
        cpp: 'cpp',
        cc: 'cpp',
        rs: 'rust',
        go: 'go',
        java: 'java',
        rb: 'ruby',
        php: 'php',
        sql: 'sql',
        toml: 'ini',
        ini: 'ini'
    };

    const loadTheme = () => {
        if (!document.querySelector('link[href*="highlight.js"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css';
            document.head.appendChild(link);
        }
    };

    const loadHighlightJs = (callback) => {
        if (typeof hljs !== 'undefined') { callback(); return; }
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js';
        script.onload = callback;
        document.head.appendChild(script);
    };

    const escapeHtml = (value) => value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    const normalizeNewlines = (value) => value.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // JSON, похожий на объект, нельзя отдавать в автоопределение: грамматика JavaScript
    // вкладывает span на каждую пару скобок, и на глубокой вложенности выделение textarea
    // перестаёт совпадать с нарисованным текстом.
    const looksLikeJson = (code) => {
        const trimmed = code.trim();
        if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return false;
        return /"(?:\\.|[^"\\\r\n])*"\s*:/.test(code);
    };

    const languageFor = (textarea, code) => {
        const name = (textarea.dataset.filename || '').toLowerCase();
        const ext = name.includes('.') ? name.split('.').pop() : '';
        if (ext === 'json' || ext === 'jsonc') return 'json';
        // Объект без расширения или .js/.ts: иначе highlightAuto берёт грамматику JavaScript.
        const jsonShaped = !ext || ext === 'js' || ext === 'mjs' || ext === 'cjs' || ext === 'ts';
        if (jsonShaped && looksLikeJson(code)) return 'json';
        return EXT_LANG[ext] || '';
    };

    const init = () => {
        document.querySelectorAll('.code-editor').forEach(setupTextarea);
    };

    const setupTextarea = (textarea) => {
        if (textarea.dataset.hljsProcessed) return;
        textarea.dataset.hljsProcessed = 'true';

        const wrapper = document.createElement('div');
        wrapper.className = 'code-editor-shell';

        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(textarea);

        const pre = document.createElement('pre');
        pre.className = 'hljs hljs-backdrop';
        pre.setAttribute('aria-hidden', 'true');

        const codeElement = document.createElement('code');
        pre.appendChild(codeElement);

        const lineNumbers = document.createElement('div');
        lineNumbers.className = 'line-numbers';

        wrapper.insertBefore(lineNumbers, textarea);
        wrapper.insertBefore(pre, textarea);

        textarea.style.background = 'transparent';
        textarea.style.color = 'transparent';
        textarea.style.caretColor = '#ffffff';
        textarea.style.position = 'relative';
        textarea.style.zIndex = '1';

        const paintLines = (code) => {
            const linesCount = code ? code.split('\n').length : 1;
            lineNumbers.textContent = '';
            for (let i = 1; i <= linesCount; i++) {
                lineNumbers.appendChild(document.createTextNode(String(i)));
                if (i !== linesCount) lineNumbers.appendChild(document.createElement('br'));
            }
        };

        const syncScroll = () => {
            const style = window.getComputedStyle(textarea);
            const borders = (parseFloat(style.borderLeftWidth) || 0) + (parseFloat(style.borderRightWidth) || 0);
            const scrollbarWidth = textarea.offsetWidth - textarea.clientWidth - borders;
            pre.style.setProperty('--hl-sbw', Math.max(0, scrollbarWidth) + 'px');
            pre.scrollTop = textarea.scrollTop;
            pre.scrollLeft = textarea.scrollLeft;
            lineNumbers.scrollTop = textarea.scrollTop;
        };

        const updateHighlight = () => {
            const code = textarea.value;
            if (!code) {
                codeElement.textContent = '';
                paintLines('');
                syncScroll();
                return;
            }

            const language = languageFor(textarea, code);
            let html;
            try {
                if (language && hljs.getLanguage(language)) {
                    html = hljs.highlight(code, { language: language, ignoreIllegals: true }).value;
                } else {
                    html = hljs.highlightAuto(code).value;
                }
            } catch (err) {
                html = escapeHtml(code);
            }

            codeElement.innerHTML = html;
            if (normalizeNewlines(codeElement.textContent) !== normalizeNewlines(code)) {
                codeElement.textContent = code;
            }
            paintLines(code);
            syncScroll();
        };

        let frame = 0;
        const scheduleHighlight = () => {
            if (frame) cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
                frame = 0;
                updateHighlight();
            });
        };

        updateHighlight();
        textarea.addEventListener('input', scheduleHighlight);
        textarea.addEventListener('scroll', syncScroll);
        document.addEventListener('selectionchange', () => {
            if (document.activeElement === textarea) syncScroll();
        });
        if (typeof ResizeObserver !== 'undefined') {
            const observer = new ResizeObserver(syncScroll);
            observer.observe(textarea);
        } else {
            window.addEventListener('resize', syncScroll);
        }
    };

    loadTheme();
    loadHighlightJs(init);
})();
