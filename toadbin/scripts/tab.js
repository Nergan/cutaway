// tab.js - добавляет поддержку клавиш Tab, Shift + Tab, автозакрытие скобок и правильное поведение при Enter в поле ввода кода
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

            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();
                
                if (event.shiftKey) {
                    // Обработка Shift + Tab: удаляем отступ
                    let newValue, newCursorStart, newCursorEnd;

                    if (start !== end) {
                        // Если выделено несколько строк
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
            } else if (event.key === 'Enter') {
                // Обработка Enter: вставка отступа при открывающих/закрывающих скобках
                event.preventDefault();

                const currentChar = value.charAt(start - 1);
                const nextChar = value.charAt(start);
                
                // Проверяем, если символ перед курсором является открывающей скобкой, добавляем отступ в новой строке
                if (['{', '[', '(', '"', "'", '`'].includes(currentChar)) {
                    // Вставляем новую строку с отступом
                    const newLine = '\n' + indent + value.substring(start);
                    this.value = value.substring(0, start) + newLine;
                    this.selectionStart = this.selectionEnd = start + indent.length + 1;
                }
                // Проверяем, если символ перед курсором является закрывающей скобкой, тоже вставляем новую строку с отступом
                else if (['}', ']', ')', '"', "'", '`'].includes(currentChar)) {
                    const newLine = '\n' + value.substring(start);
                    this.value = value.substring(0, start) + newLine;
                    this.selectionStart = this.selectionEnd = start + indent.length;
                } else {
                    // Для всех других случаев просто вставляем новую строку с отступом
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
