(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, tab.js will not work');
            return;
        }

        const indent = '    '; // 4 пробела
        const closingPairs = {
            '(': ')',
            '[': ']',
            '{': '}',
            '<': '>',
            "'": "'",
            '"': '"',
            '`': '`'
        };

        // Обработчик нажатия клавиш
        codeInput.addEventListener('keydown', function(event) {
            const start = this.selectionStart;
            const end = this.selectionEnd;
            const value = this.value;

            // Обработка клавиши Tab
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();

                if (event.shiftKey) {
                    // Shift + Tab: удаляем отступ
                    let newValue, newCursorStart, newCursorEnd;

                    if (start !== end) {
                        // Многострочное выделение: удаляем отступ перед каждой строкой
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
                        // Однострочное выделение: удаляем один отступ
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
                    // Обычный Tab: добавляем отступ
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
                            // Однострочное выделение: добавляем отступ в начало строки
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

                this.dispatchEvent(new Event('input', { bubbles: true }));
            } else if (event.key === 'Enter') {
                // Обработка Enter: вставка отступа при открывающих/закрывающих скобках
                event.preventDefault();

                const currentChar = value.charAt(start - 1);

                // Если перед курсором открывающая скобка, вставляем новую строку с отступом
                if (['{', '[', '(', '"', "'", '`'].includes(currentChar)) {
                    // Добавляем новую строку с отступом
                    const newLine = '\n' + indent + value.substring(start);
                    this.value = value.substring(0, start) + newLine;
                    this.selectionStart = this.selectionEnd = start + indent.length + 1;
                } else if (['}', ']', ')', '"', "'", '`'].includes(currentChar)) {
                    // Если перед курсором закрывающая скобка, вставляем новую строку с отступом
                    const newLine = '\n' + value.substring(start);
                    this.value = value.substring(0, start) + newLine;
                    this.selectionStart = this.selectionEnd = start + indent.length;
                } else {
                    // Вставляем новую строку с отступом для других случаев
                    this.value = value.substring(0, start) + '\n' + indent + value.substring(start);
                    this.selectionStart = this.selectionEnd = start + indent.length + 1;
                }

                this.dispatchEvent(new Event('input', { bubbles: true }));
            } else if (closingPairs[event.key]) {
                // Автозакрытие скобок и кавычек
                event.preventDefault();

                const cursorPosition = this.selectionStart;
                const currentChar = value.charAt(cursorPosition - 1);

                if (closingPairs[currentChar] && value.charAt(cursorPosition) !== closingPairs[currentChar]) {
                    this.value = value.substring(0, cursorPosition) + closingPairs[currentChar] + value.substring(cursorPosition);
                    this.selectionStart = this.selectionEnd = cursorPosition;
                } else {
                    this.value = value.substring(0, cursorPosition) + event.key + closingPairs[event.key] + value.substring(cursorPosition);
                    this.selectionStart = this.selectionEnd = cursorPosition + 1;
                }

                this.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });

        console.log('Toadbin tab script loaded. Tab, Shift+Tab, Auto-closing brackets, and Enter with indentation now supported.');
    });
})();
