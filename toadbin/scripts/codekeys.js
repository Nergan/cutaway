(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, tab.js will not work');
            return;
        }

        const indent = '    '; // 4 пробела
        const openBrackets = ['(', '[', '{', '<', "'", '"', '`'];
        const closeBrackets = [')', ']', '}', '>', "'", '"', '`'];
        const bracketPairs = {
            '(': ')',
            '[': ']',
            '{': '}',
            '<': '>',
            "'": "'",
            '"': '"',
            '`': '`'
        };
        const reversePairs = Object.fromEntries(
            Object.entries(bracketPairs).map(([open, close]) => [close, open])
        );

        // Вспомогательная функция для получения информации о строке по позиции
        function getLineInfo(text, pos) {
            const lines = text.split('\n');
            const starts = [];
            let currentPos = 0;
            for (let i = 0; i < lines.length; i++) {
                starts[i] = currentPos;
                currentPos += lines[i].length + 1; // +1 за \n
            }
            // Находим строку, содержащую pos (включая позицию на \n)
            for (let i = 0; i < lines.length; i++) {
                const lineEnd = starts[i] + lines[i].length;
                if (pos >= starts[i] && pos <= lineEnd) {
                    return {
                        lineIndex: i,
                        col: pos - starts[i],
                        lineStart: starts[i],
                        line: lines[i]
                    };
                }
            }
            // Если pos за пределами (например, в конце текста без \n)
            const lastLineIndex = lines.length - 1;
            return {
                lineIndex: lastLineIndex,
                col: lines[lastLineIndex].length,
                lineStart: starts[lastLineIndex],
                line: lines[lastLineIndex]
            };
        }

        // Обработчик нажатия клавиш
        codeInput.addEventListener('keydown', function(event) {
            const start = this.selectionStart;
            const end = this.selectionEnd;
            const value = this.value;

            // --- Ctrl+L: выделить текущую строку ---
            if (event.ctrlKey && event.key === 'l') {
                event.preventDefault();
                const lineInfo = getLineInfo(value, start);
                const lineStart = lineInfo.lineStart;
                const lineEnd = lineStart + lineInfo.line.length;
                this.selectionStart = lineStart;
                this.selectionEnd = lineEnd;
                return;
            }

            // --- Обработка Tab и Shift+Tab для выделения ---
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();

                if (event.shiftKey) {
                    // Shift+Tab: удаляем отступ из начала каждой затронутой строки
                    if (start === end) {
                        // Если нет выделения, пытаемся удалить отступ перед курсором (в текущей строке)
                        const lineInfo = getLineInfo(value, start);
                        const line = lineInfo.line;
                        if (line.startsWith(indent)) {
                            const newLine = line.substring(indent.length);
                            const newValue = value.substring(0, lineInfo.lineStart) + newLine + value.substring(lineInfo.lineStart + line.length);
                            const newCursorPos = lineInfo.lineStart + Math.max(0, start - lineInfo.lineStart - indent.length);
                            this.value = newValue;
                            this.selectionStart = this.selectionEnd = newCursorPos;
                            this.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        return;
                    }

                    // Есть выделение: обрабатываем все строки в диапазоне
                    const lines = value.split('\n');
                    const starts = [];
                    let acc = 0;
                    for (let i = 0; i < lines.length; i++) {
                        starts[i] = acc;
                        acc += lines[i].length + 1;
                    }

                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1); // последний символ выделения

                    let firstLine = startInfo.lineIndex;
                    let lastLine = endInfo.lineIndex;

                    // Модифицируем строки
                    for (let i = firstLine; i <= lastLine; i++) {
                        if (lines[i].startsWith(indent)) {
                            lines[i] = lines[i].substring(indent.length);
                        }
                    }

                    // Собираем новый текст
                    const newValue = lines.join('\n');

                    // Вычисляем новые позиции курсора/выделения
                    // Сначала вычислим новые начала строк
                    const newStarts = [];
                    let newAcc = 0;
                    for (let i = 0; i < lines.length; i++) {
                        newStarts[i] = newAcc;
                        newAcc += lines[i].length + 1;
                    }

                    // Корректируем колонки с учётом удалённого отступа
                    let newStartCol = startInfo.col;
                    let newEndCol = endInfo.col;
                    if (startInfo.lineIndex >= firstLine && startInfo.lineIndex <= lastLine) {
                        newStartCol = Math.max(0, startInfo.col - indent.length);
                    }
                    if (endInfo.lineIndex >= firstLine && endInfo.lineIndex <= lastLine) {
                        newEndCol = Math.max(0, endInfo.col - indent.length);
                    }

                    const newStart = newStarts[startInfo.lineIndex] + newStartCol;
                    const newEnd = newStarts[endInfo.lineIndex] + newEndCol;

                    this.value = newValue;
                    this.selectionStart = newStart;
                    this.selectionEnd = newEnd;
                    this.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    // Tab без Shift: добавляем отступ в начало каждой затронутой строки
                    if (start === end) {
                        // Просто вставляем отступ в позицию курсора
                        const newValue = value.substring(0, start) + indent + value.substring(end);
                        this.value = newValue;
                        this.selectionStart = this.selectionEnd = start + indent.length;
                        this.dispatchEvent(new Event('input', { bubbles: true }));
                        return;
                    }

                    // Есть выделение: обрабатываем все строки в диапазоне
                    const lines = value.split('\n');
                    const starts = [];
                    let acc = 0;
                    for (let i = 0; i < lines.length; i++) {
                        starts[i] = acc;
                        acc += lines[i].length + 1;
                    }

                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1);

                    let firstLine = startInfo.lineIndex;
                    let lastLine = endInfo.lineIndex;

                    // Добавляем отступ к каждой строке диапазона
                    for (let i = firstLine; i <= lastLine; i++) {
                        lines[i] = indent + lines[i];
                    }

                    const newValue = lines.join('\n');

                    // Вычисляем новые начала строк
                    const newStarts = [];
                    let newAcc = 0;
                    for (let i = 0; i < lines.length; i++) {
                        newStarts[i] = newAcc;
                        newAcc += lines[i].length + 1;
                    }

                    // Колонки увеличиваются на длину отступа, если строка в диапазоне
                    let newStartCol = startInfo.col;
                    let newEndCol = endInfo.col;
                    if (startInfo.lineIndex >= firstLine && startInfo.lineIndex <= lastLine) {
                        newStartCol += indent.length;
                    }
                    if (endInfo.lineIndex >= firstLine && endInfo.lineIndex <= lastLine) {
                        newEndCol += indent.length;
                    }

                    const newStart = newStarts[startInfo.lineIndex] + newStartCol;
                    const newEnd = newStarts[endInfo.lineIndex] + newEndCol;

                    this.value = newValue;
                    this.selectionStart = newStart;
                    this.selectionEnd = newEnd;
                    this.dispatchEvent(new Event('input', { bubbles: true }));
                }
                return;
            }

            // --- Обработка Enter с умным отступом для скобок ---
            if (event.key === 'Enter') {
                event.preventDefault();

                const before = value.substring(0, start);
                const after = value.substring(end);

                // Проверяем, находимся ли мы между открывающей и закрывающей скобками (без промежуточных символов)
                const prevChar = before.slice(-1);
                const nextChar = after[0] || '';

                if (openBrackets.includes(prevChar) && closeBrackets.includes(nextChar) && bracketPairs[prevChar] === nextChar) {
                    // Случай: {|}  (где | курсор)
                    // Определяем отступ перед открывающей скобкой
                    const lineInfo = getLineInfo(value, start - 1); // позиция перед скобкой
                    const lineStart = lineInfo.lineStart;
                    const lineText = lineInfo.line;
                    const leadingWhitespace = lineText.match(/^\s*/)[0]; // пробелы в начале строки

                    // Формируем новый текст:
                    // открывающая скобка, затем \n, затем отступ+indent, затем \n, затем отступ и закрывающая скобка
                    const newText = before + '\n' + leadingWhitespace + indent + '\n' + leadingWhitespace + nextChar + after.slice(1);
                    const newCursorPos = before.length + 1 + leadingWhitespace.length + indent.length; // после отступа на второй строке

                    this.value = newText;
                    this.selectionStart = this.selectionEnd = newCursorPos;
                } else {
                    // Обычный Enter: вставляем перевод строки и повторяем отступ предыдущей строки
                    const lineInfo = getLineInfo(value, start);
                    const lineText = lineInfo.line;
                    const leadingWhitespace = lineText.match(/^\s*/)[0];
                    const newText = before + '\n' + leadingWhitespace + after;
                    const newCursorPos = start + 1 + leadingWhitespace.length; // после вставленного отступа
                    this.value = newText;
                    this.selectionStart = this.selectionEnd = newCursorPos;
                }

                this.dispatchEvent(new Event('input', { bubbles: true }));
                return;
            }

            // --- Автозакрытие скобок и кавычек ---
            if (event.key.length === 1 && (openBrackets.includes(event.key) || closeBrackets.includes(event.key))) {
                event.preventDefault();

                const cursorPos = start;
                const nextChar = value[cursorPos] || '';

                if (openBrackets.includes(event.key)) {
                    // Ввод открывающего символа
                    if (start !== end) {
                        // Есть выделение: оборачиваем его в скобки
                        const selected = value.substring(start, end);
                        const newValue = value.substring(0, start) + event.key + selected + bracketPairs[event.key] + value.substring(end);
                        this.value = newValue;
                        // Оставляем выделение на исходном тексте (он теперь внутри скобок)
                        this.selectionStart = start + 1;
                        this.selectionEnd = end + 1;
                    } else {
                        // Нет выделения: вставляем пару и ставим курсор между ними
                        const newValue = value.substring(0, cursorPos) + event.key + bracketPairs[event.key] + value.substring(cursorPos);
                        this.value = newValue;
                        this.selectionStart = this.selectionEnd = cursorPos + 1;
                    }
                } else if (closeBrackets.includes(event.key)) {
                    // Ввод закрывающего символа
                    // Если следующий символ уже является таким же закрывающим, просто перемещаем курсор
                    if (nextChar === event.key) {
                        this.selectionStart = this.selectionEnd = cursorPos + 1;
                    } else {
                        // Иначе вставляем символ
                        const newValue = value.substring(0, cursorPos) + event.key + value.substring(cursorPos);
                        this.value = newValue;
                        this.selectionStart = this.selectionEnd = cursorPos + 1;
                    }
                }

                this.dispatchEvent(new Event('input', { bubbles: true }));
                return;
            }
        });

        console.log('Toadbin tab script loaded. Tab, Shift+Tab, Auto-closing brackets, Enter with indentation, and Ctrl+L now supported.');
    });
})();