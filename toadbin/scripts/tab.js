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

                let newValue, newCursorStart, newCursorEnd;

                if (start !== end) {
                    const selectedText = value.substring(start, end);
                    if (selectedText.includes('\n')) {
                        // Многострочное выделение: добавляем отступ перед каждой строкой
                        const lines = selectedText.split('\n');
                        const indentedLines = lines.map(line => indent + line);
                        const indentedText = indentedLines.join('\n');

                        newValue = value.substring(0, start) + indentedText + value.substring(end);
                        newCursorStart = start;
                        newCursorEnd = start + indentedText.length;
                    } else {
                        // Однострочное выделение: заменяем выделенный текст отступом
                        newValue = value.substring(0, start) + indent + value.substring(end);
                        newCursorStart = start + indent.length;
                        newCursorEnd = newCursorStart;
                    }
                } else {
                    // Без выделения: вставляем отступ в позицию курсора
                    newValue = value.substring(0, start) + indent + value.substring(end);
                    newCursorStart = start + indent.length;
                    newCursorEnd = newCursorStart;
                }

                // Применяем изменения
                this.value = newValue;
                this.selectionStart = newCursorStart;
                this.selectionEnd = newCursorEnd;

                // Вызываем событие input для обновления подсветки и счётчика символов
                this.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });

        console.log('Toadbin tab script loaded. Tab now indents with 4 spaces (multi-line supported).');
    });
})();