(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, tab.js will not work');
            return;
        }

        const indent = '    '; // 4 пробела
        const autoClosePairs = {
            '(': ')',
            '[': ']',
            '{': '}',
            '<': '>',
            "'": "'",
            '"': '"',
            '`': '`'
        };

        // Обработчик для закрытия символов
        function handleAutoClose(event) {
            const start = codeInput.selectionStart;
            const end = codeInput.selectionEnd;
            const value = codeInput.value;
            const cursorChar = value[start - 1];

            // Проверяем, нужно ли закрыть символ
            if (autoClosePairs[cursorChar] && start === end) {
                // Проверяем, если следующий символ уже закрывающий
                if (value[start] !== autoClosePairs[cursorChar]) {
                    codeInput.value = value.slice(0, start) + autoClosePairs[cursorChar] + value.slice(end);
                    codeInput.selectionStart = codeInput.selectionEnd = start;
                    event.preventDefault();
                }
            }
        }

        // Обработчик для Enter
        function handleEnter(event) {
            const start = codeInput.selectionStart;
            const end = codeInput.selectionEnd;
            const value = codeInput.value;
            const cursorChar = value[start - 1];
            const indentSpace = codeInput.value.substring(0, start).split('\n').pop().match(/^ */)[0];

            // Проверяем, внутри ли мы конструкции и если да, то добавляем отступы
            if (['{', '[', '(', '<'].includes(cursorChar)) {
                codeInput.value = value.slice(0, start) + '\n' + indent + value.slice(start);
                codeInput.selectionStart = codeInput.selectionEnd = start + indent.length;
                event.preventDefault();
            }
        }

        // Обработчик для изменения отступов с использованием Tab и Shift+Tab
        codeInput.addEventListener('keydown', function(event) {
            const start = this.selectionStart;
            const end = this.selectionEnd;
            const value = this.value;

            // Обработка Tab
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();
                
                if (event.shiftKey) {
                    // Shift + Tab: убираем отступ
                    let newValue, newCursorStart, newCursorEnd;

                    if (start !== end) {
                        const selectedText = value.substring(start, end);
                        const lines = selectedText.split('\n');
                        const unindentedLines = lines.map(line => line.startsWith(indent) ? line.substring(indent.length) : line);
                        const unindentedText = unindentedLines.join('\n');

                        newValue = value.substring(0, start) + unindentedText + value.substring(end);
                        newCursorStart = start;
                        newCursorEnd = start + unindentedText.length;
                    } else {
                        const line = value.substring(start, end);
                        const unindentedLine = line.startsWith(indent) ? line.substring(indent.length) : line;

                        newValue = value.substring(0, start) + unindentedLine + value.substring(end);
                        newCursorStart = start;
                        newCursorEnd = newCursorStart + unindentedLine.length;
                    }

                    this.value = newValue;
                    this.selectionStart = newCursorStart;
                    this.selectionEnd = newCursorEnd;
                } else {
                    // Tab: добавляем отступ
                    let newValue, newCursorStart, newCursorEnd;

                    if (start !== end) {
                        const selectedText = value.substring(start, end);
                        if (selectedText.includes('\n')) {
                            const lines = selectedText.split('\n');
                            const indentedLines = lines.map(line => indent + line);
                            const indentedText = indentedLines.join('\n');

                            newValue = value.substring(0, start) + indentedText + value.substring(end);
                            newCursorStart = start;
                            newCursorEnd = start + indentedText.length;
                        } else {
                            newValue = value.substring(0, start) + indent + value.substring(end);
                            newCursorStart = start + indent.length;
                            newCursorEnd = newCursorStart;
                        }
                    } else {
                        newValue = value.substring(0, start) + indent + value.substring(end);
                        newCursorStart = start + indent.length;
                        newCursorEnd = newCursorStart;
                    }

                    this.value = newValue;
                    this.selectionStart = newCursorStart;
                    this.selectionEnd = newCursorEnd;
                }
            }

            // Выбор всей строки по Ctrl + L
            if (event.key === 'l' && event.ctrlKey) {
                event.preventDefault();
                const lineStart = value.lastIndexOf('\n', start) + 1;
                const lineEnd = value.indexOf('\n', start);
                const line = value.substring(lineStart, lineEnd === -1 ? value.length : lineEnd);
                this.selectionStart = lineStart;
                this.selectionEnd = lineEnd === -1 ? value.length : lineEnd;
            }
        });

        // Обработка ввода закрывающих символов
        codeInput.addEventListener('input', handleAutoClose);

        // Обработка Enter для отступа внутри блоков
        codeInput.addEventListener('keydown', handleEnter);

        console.log('Tab script loaded with auto-close, indenting, and tab features.');
    });
})();
