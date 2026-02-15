// tab.js - добавляет поддержку клавиш Tab и Shift + Tab в поле ввода кода
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
            const start = this.selectionStart;
            const end = this.selectionEnd;
            const value = this.value;

            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();
                
                if (event.shiftKey) {
                    // Обработка Shift + Tab: удаляем отступ
                    let newValue, newCursorStart, newCursorEnd;

                    if (start !== end) {
                        // Если выделен несколько строк
                        const selectedText = value.substring(start, end);
                        const lines = selectedText.split('\n');
                        const unindentedLines = lines.map(line => {
                            // Убираем отступ, если он есть
                            return line.startsWith(indent) ? line.substring(indent.length) : line;
                        });
                        const unindentedText = unindentedLines.join('\n');

                        newValue = value.substring(0, start) + unindentedText + value.substring(end);
                        newCursorStart = start;
                        newCursorEnd = start + unindentedText.length;
                    } else {
                        // Если выделена одна строка
                        const line = value.substring(start, end);
                        const unindentedLine = line.startsWith(indent) ? line.substring(indent.length) : line;
                        
                        newValue = value.substring(0, start) + unindentedLine + value.substring(end);
                        newCursorStart = start;
                        newCursorEnd = newCursorStart + unindentedLine.length;
                    }

                    // Применяем изменения
                    this.value = newValue;
                    this.selectionStart = newCursorStart;
                    this.selectionEnd = newCursorEnd;
                } else {
                    // Обработка обычного Tab: добавляем отступ
                    let newValue, newCursorStart, newCursorEnd;

                    if (start !== end) {
                        // Многострочное выделение: добавляем отступ перед каждой строкой
                        const selectedText = value.substring(start, end);
                        if (selectedText.includes('\n')) {
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
                }

                // Вызываем событие input для обновления подсветки и счётчика символов
                this.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });

        console.log('Toadbin tab script loaded. Tab now indents (Shift+Tab removes indentation, multi-line supported).');
    });
})();
