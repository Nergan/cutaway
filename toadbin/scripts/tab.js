// tab.js - добавляет поддержку клавиши Tab в поле ввода кода
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, tab.js will not work');
            return;
        }

        const indent = '    '; // 4 пробела

        codeInput.addEventListener('keydown', function(event) {
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();

                const start = this.selectionStart;
                const end = this.selectionEnd;
                const value = this.value;

                // Если есть выделение, проверяем, многострочное ли оно
                if (start !== end) {
                    const selectedText = value.substring(start, end);
                    if (selectedText.includes('\n')) {
                        // Многострочное выделение: добавляем отступ перед каждой строкой
                        const lines = selectedText.split('\n');
                        const indentedLines = lines.map(line => indent + line);
                        const indentedText = indentedLines.join('\n');

                        this.value = value.substring(0, start) + indentedText + value.substring(end);

                        // Выделяем весь изменённый блок
                        this.selectionStart = start;
                        this.selectionEnd = start + indentedText.length;
                        return;
                    }
                }

                // Если выделение отсутствует или однострочное: вставляем отступ в позицию курсора
                this.value = value.substring(0, start) + indent + value.substring(end);
                this.selectionStart = this.selectionEnd = start + indent.length;
            }
        });

        console.log('Toadbin tab script loaded. Tab now indents with 4 spaces (multi-line supported).');
    });
})();