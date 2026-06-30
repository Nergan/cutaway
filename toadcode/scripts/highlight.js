(function() {
    'use strict';

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

    const init = () => {
        document.querySelectorAll('.code-editor').forEach(setupTextarea);
    };

    const setupTextarea = (textarea) => {
        if (textarea.dataset.hljsProcessed) return;
        textarea.dataset.hljsProcessed = 'true';

        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        wrapper.style.display = 'inline-block';
        wrapper.style.width = '100%';
        wrapper.style.height = '100%';

        textarea.parentNode.insertBefore(wrapper, textarea);
        wrapper.appendChild(textarea);
        textarea.style.width = '100%';
        textarea.style.height = '100%';

        const pre = document.createElement('pre');
        pre.className = 'hljs';
        pre.style.position = 'absolute';
        pre.style.top = '0'; pre.style.left = '0'; pre.style.right = '0'; pre.style.bottom = '0';
        pre.style.margin = '0'; pre.style.pointerEvents = 'none';
        pre.style.overflow = 'hidden'; pre.style.whiteSpace = 'pre-wrap'; pre.style.wordWrap = 'break-word';

        const style = window.getComputedStyle(textarea);
        pre.style.padding = style.padding; pre.style.fontFamily = style.fontFamily;
        pre.style.fontSize = style.fontSize; pre.style.lineHeight = style.lineHeight;
        pre.style.boxSizing = style.boxSizing; pre.style.border = style.border;
        pre.style.borderRadius = style.borderRadius; pre.style.overflowWrap = style.overflowWrap;

        const codeElement = document.createElement('code');
        codeElement.style.margin = '0'; codeElement.style.padding = '0';
        pre.appendChild(codeElement);

        const lineNumbers = document.createElement('div');
        lineNumbers.className = 'line-numbers custom-font';
        
        // Fix: Insert elements in the correct order to avoid DOM Node errors
        wrapper.insertBefore(lineNumbers, textarea);
        wrapper.insertBefore(pre, textarea);

        textarea.style.background = 'transparent';
        textarea.style.color = 'transparent';
        textarea.style.caretColor = '#ffffff';
        textarea.style.position = 'relative';
        textarea.style.zIndex = '1';

        const updateHighlight = () => {
            const code = textarea.value;
            if (!code) { 
                codeElement.textContent = ''; 
                lineNumbers.innerHTML = '1';
                return; 
            }
            codeElement.innerHTML = hljs.highlightAuto(code).value;
            const linesCount = code.split('\n').length;
            lineNumbers.innerHTML = Array.from({length: linesCount}, (_, i) => i + 1).join('<br>');
        };

        const syncScroll = () => {
            pre.scrollTop = textarea.scrollTop;
            pre.scrollLeft = textarea.scrollLeft;
            lineNumbers.scrollTop = textarea.scrollTop;
        };

        updateHighlight();
        textarea.addEventListener('input', updateHighlight);
        textarea.addEventListener('scroll', syncScroll);
    };

    loadTheme();
    loadHighlightJs(init);
})();