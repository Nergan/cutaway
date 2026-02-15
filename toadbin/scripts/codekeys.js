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

        // Безопасная вставка текста через execCommand (сохраняет историю undo)
        function insertTextAtSelection(text) {
            // execCommand('insertText', false, text) заменяет текущее выделение текстом
            // и добавляет действие в историю undo
            if (document.execCommand('insertText', false, text)) {
                return true;
            } else {
                // Fallback: если execCommand не сработал, используем старый способ
                const start = codeInput.selectionStart;
                const end = codeInput.selectionEnd;
                const value = codeInput.value;
                codeInput.value = value.substring(0, start) + text + value.substring(end);
                codeInput.selectionStart = codeInput.selectionEnd = start + text.length;
                codeInput.dispatchEvent(new Event('input', { bubbles: true }));
                return false;
            }
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
                        // Нет выделения: пытаемся удалить отступ перед курсором (в текущей строке)
                        const lineInfo = getLineInfo(value, start);
                        const line = lineInfo.line;
                        if (line.startsWith(indent)) {
                            const newLine = line.substring(indent.length);
                            const newStart = lineInfo.lineStart;
                            const newEnd = lineInfo.lineStart + line.length;
                            this.setSelectionRange(newStart, newEnd); // выделяем всю строку
                            insertTextAtSelection(newLine); // заменяем на строку без отступа
                            // Восстанавливаем курсор примерно на том же месте (с учётом удалённого отступа)
                            const newCursor = lineInfo.lineStart + Math.max(0, start - lineInfo.lineStart - indent.length);
                            this.setSelectionRange(newCursor, newCursor);
                        }
                        return;
                    }

                    // Есть выделение: обрабатываем все строки в диапазоне
                    const lines = value.split('\n');
                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1);

                    let firstLine = startInfo.lineIndex;
                    let lastLine = endInfo.lineIndex;

                    // Сохраняем оригинальные строки для расчёта новых позиций
                    const originalLines = lines.slice(firstLine, lastLine + 1);
                    const modifiedLines = originalLines.map(line => 
                        line.startsWith(indent) ? line.substring(indent.length) : line
                    );

                    // Заменяем выделенный диапазон новыми строками
                    const before = value.substring(0, startInfo.lineStart);
                    const after = value.substring(endInfo.lineStart + endInfo.line.length + (lastLine < lines.length - 1 ? 1 : 0)); // + \n если не последняя
                    const newText = modifiedLines.join('\n');
                    const fullText = before + newText + after;

                    // Устанавливаем выделение на весь диапазон строк и заменяем
                    const rangeStart = startInfo.lineStart;
                    const rangeEnd = endInfo.lineStart + endInfo.line.length + (lastLine - firstLine); // приблизительно, но лучше точно
                    this.setSelectionRange(rangeStart, rangeEnd);
                    insertTextAtSelection(newText);

                    // Восстанавливаем выделение на ту же область (приблизительно)
                    // Новые позиции: начало остаётся тем же, конец сдвигается на разницу длин
                    const newEndPos = rangeStart + newText.length;
                    this.setSelectionRange(rangeStart, newEndPos);
                } else {
                    // Tab без Shift: добавляем отступ в начало каждой затронутой строки
                    if (start === end) {
                        // Просто вставляем отступ в позицию курсора
                        insertTextAtSelection(indent);
                        return;
                    }

                    // Есть выделение: обрабатываем все строки в диапазоне
                    const lines = value.split('\n');
                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1);

                    let firstLine = startInfo.lineIndex;
                    let lastLine = endInfo.lineIndex;

                    const originalLines = lines.slice(firstLine, lastLine + 1);
                    const modifiedLines = originalLines.map(line => indent + line);

                    const before = value.substring(0, startInfo.lineStart);
                    const after = value.substring(endInfo.lineStart + endInfo.line.length + (lastLine < lines.length - 1 ? 1 : 0));
                    const newText = modifiedLines.join('\n');
                    const rangeStart = startInfo.lineStart;
                    const rangeEnd = endInfo.lineStart + endInfo.line.length + (lastLine - firstLine);
                    this.setSelectionRange(rangeStart, rangeEnd);
                    insertTextAtSelection(newText);
                    this.setSelectionRange(rangeStart, rangeStart + newText.length);
                }
                return;
            }

            // --- Обработка Enter ---
            if (event.key === 'Enter') {
                event.preventDefault();

                const before = value.substring(0, start);
                const after = value.substring(end);

                // Проверяем специальный случай: курсор между открывающей и закрывающей скобками (например, {|})
                const prevChar = before.slice(-1);
                const nextChar = after[0] || '';

                if (openBrackets.includes(prevChar) && closeBrackets.includes(nextChar) && bracketPairs[prevChar] === nextChar) {
                    // Случай: {|} 
                    const lineInfo = getLineInfo(value, start - 1);
                    const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];

                    // Формируем новый текст: открывающая скобка, \n, отступ+indent, \n, отступ и закрывающая скобка
                    const newText = before + '\n' + leadingWhitespace + indent + '\n' + leadingWhitespace + nextChar + after.slice(1);
                    // Заменяем текущее выделение (нулевой длины) на новый текст
                    insertTextAtSelection(newText);
                    // Устанавливаем курсор на второй строке после отступа
                    const newCursorPos = before.length + 1 + leadingWhitespace.length + indent.length;
                    this.setSelectionRange(newCursorPos, newCursorPos);
                    return;
                }

                // Специальный случай: перед курсором двоеточие (с возможными пробелами)
                if (/:\s*$/.test(before)) {
                    const lineInfo = getLineInfo(value, start);
                    const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];
                    
                    // Удаляем пробелы в конце before (после двоеточия)
                    const beforeTrimmed = before.replace(/\s+$/, '');
                    // Удаляем начальные пробелы из after
                    const afterTrimmed = after.trimStart();
                    
                    // Формируем новый текст: before без пробелов + \n + отступ + indent + after без пробелов
                    const newText = beforeTrimmed + '\n' + leadingWhitespace + indent + afterTrimmed;
                    insertTextAtSelection(newText);
                    
                    // Курсор ставим после отступа на новой строке, перед afterTrimmed
                    const newCursorPos = beforeTrimmed.length + 1 + leadingWhitespace.length + indent.length;
                    this.setSelectionRange(newCursorPos, newCursorPos);
                    return;
                }

                // Обычный Enter: вставляем перевод строки и повторяем отступ предыдущей строки
                const lineInfo = getLineInfo(value, start);
                const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];
                const newText = '\n' + leadingWhitespace;
                insertTextAtSelection(newText);
                // Курсор остаётся после вставленного отступа (автоматически после execCommand)
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
                        const newText = event.key + selected + bracketPairs[event.key];
                        insertTextAtSelection(newText);
                        // Оставляем выделение на исходном тексте (он теперь внутри скобок)
                        this.setSelectionRange(start + 1, end + 1);
                    } else {
                        // Нет выделения: вставляем пару и ставим курсор между ними
                        const newText = event.key + bracketPairs[event.key];
                        insertTextAtSelection(newText);
                        this.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    }
                } else if (closeBrackets.includes(event.key)) {
                    // Ввод закрывающего символа
                    if (nextChar === event.key) {
                        // Следующий символ уже такой же закрывающий — просто перепрыгиваем
                        this.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    } else {
                        // Иначе вставляем символ
                        insertTextAtSelection(event.key);
                    }
                }
                return;
            }
        });

        console.log('Toadbin tab script loaded. Tab, Shift+Tab, Auto-closing brackets, Enter with indentation (including after colon), and Ctrl+L now supported. Undo/redo works via execCommand.');
    });
})();