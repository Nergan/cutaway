document.addEventListener('DOMContentLoaded', function() {
    // Загружаем Highlight.js с темной темой
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css';
    document.head.appendChild(link);
    
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js';
    
    script.onload = function() {
        // Загружаем дополнительные языки
        const langScripts = [
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/python.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/javascript.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/java.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/cpp.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/php.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/html.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/css.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/sql.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/bash.min.js'
        ];
        
        let loaded = 0;
        const total = langScripts.length;
        
        function loadNext() {
            if (loaded >= total) {
                initHighlighting();
                return;
            }
            
            const langScript = document.createElement('script');
            langScript.src = langScripts[loaded];
            langScript.onload = loadNext;
            langScript.onerror = loadNext;
            document.head.appendChild(langScript);
            loaded++;
        }
        
        loadNext();
    };
    
    document.head.appendChild(script);
    
    function initHighlighting() {
        document.querySelectorAll('.code-editor').forEach(textarea => {
            const code = textarea.value;
            
            // Определяем язык с помощью Highlight.js
            const result = hljs.highlightAuto(code);
            
            // Создаем контейнер для подсветки
            const pre = document.createElement('pre');
            const codeElement = document.createElement('code');
            
            codeElement.className = result.language ? `language-${result.language}` : '';
            codeElement.innerHTML = result.value;
            
            pre.appendChild(codeElement);
            
            // Вставляем перед textarea
            textarea.parentNode.insertBefore(pre, textarea);
            
            // Скрываем textarea
            textarea.style.display = 'none';
            
            // УДАЛЕНО: блок создания метки с языком
            
            // Создаем скрытый input для отправки формы
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = textarea.name || 'code';
            hiddenInput.value = code;
            pre.appendChild(hiddenInput);
        });
    }
});