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

        // Вспомогательная функция: информация о строке по позиции
        function getLineInfo(text, pos) {
            const lines = text.split('\n');
            const starts = [];
            let currentPos = 0;
            for (let i = 0; i < lines.length; i++) {
                starts[i] = currentPos;
                currentPos += lines[i].length + 1; // +1 за '\n'
            }
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
            const lastLineIndex = lines.length - 1;
            return {
                lineIndex: lastLineIndex,
                col: lines[lastLineIndex].length,
                lineStart: starts[lastLineIndex],
                line: lines[lastLineIndex]
            };
        }

        // Безопасная вставка текста с сохранением истории undo/redo
        function insertTextAtSelection(text) {
            if (document.execCommand('insertText', false, text)) {
                return true;
            } else {
                // fallback
                const start = codeInput.selectionStart;
                const end = codeInput.selectionEnd;
                const value = codeInput.value;
                codeInput.value = value.substring(0, start) + text + value.substring(end);
                codeInput.selectionStart = codeInput.selectionEnd = start + text.length;
                codeInput.dispatchEvent(new Event('input', { bubbles: true }));
                return false;
            }
        }

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

            // --- Обработка Tab и Shift+Tab ---
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();

                if (event.shiftKey) {
                    // Shift+Tab: удаляем отступ из начала каждой затронутой строки
                    if (start === end) {
                        // Без выделения: удаляем отступ в текущей строке, если есть
                        const lineInfo = getLineInfo(value, start);
                        const line = lineInfo.line;
                        if (line.startsWith(indent)) {
                            const newLine = line.substring(indent.length);
                            const newStart = lineInfo.lineStart;
                            const newEnd = lineInfo.lineStart + line.length;
                            this.setSelectionRange(newStart, newEnd);
                            insertTextAtSelection(newLine);
                            const newCursor = lineInfo.lineStart + Math.max(0, start - lineInfo.lineStart - indent.length);
                            this.setSelectionRange(newCursor, newCursor);
                        }
                        return;
                    }

                    // С выделением: обрабатываем все строки диапазона
                    const lines = value.split('\n');
                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1);
                    let firstLine = startInfo.lineIndex;
                    let lastLine = endInfo.lineIndex;

                    const originalLines = lines.slice(firstLine, lastLine + 1);
                    const modifiedLines = originalLines.map(line =>
                        line.startsWith(indent) ? line.substring(indent.length) : line
                    );

                    const before = value.substring(0, startInfo.lineStart);
                    const after = value.substring(endInfo.lineStart + endInfo.line.length + (lastLine < lines.length - 1 ? 1 : 0));
                    const newText = modifiedLines.join('\n');
                    const rangeStart = startInfo.lineStart;
                    const rangeEnd = endInfo.lineStart + endInfo.line.length + (lastLine - firstLine);
                    this.setSelectionRange(rangeStart, rangeEnd);
                    insertTextAtSelection(newText);
                    this.setSelectionRange(rangeStart, rangeStart + newText.length);
                } else {
                    // Tab: добавляем отступ в начало каждой затронутой строки
                    if (start === end) {
                        insertTextAtSelection(indent);
                        return;
                    }

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
                const prevChar = before.slice(-1);
                const nextChar = after[0] || '';

                // Случай 1: курсор между открывающей и закрывающей скобками (например, {|})
                if (openBrackets.includes(prevChar) && closeBrackets.includes(nextChar) && bracketPairs[prevChar] === nextChar) {
                    const openPos = start - 1;
                    const closePos = start; // позиция закрывающей скобки
                    const lineInfo = getLineInfo(value, openPos);
                    const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];

                    // Заменяем обе скобки на многострочный блок
                    this.setSelectionRange(openPos, closePos + 1);
                    const newText = prevChar + '\n' + leadingWhitespace + indent + '\n' + leadingWhitespace + nextChar;
                    insertTextAtSelection(newText);

                    const newCursorPos = openPos + 1 + leadingWhitespace.length + indent.length;
                    this.setSelectionRange(newCursorPos, newCursorPos);
                    return;
                }

                // Случай 2: двоеточие в текущей строке перед курсором (только пробелы между ними)
                const lineInfo = getLineInfo(value, start);
                const line = lineInfo.line;
                const col = lineInfo.col;
                const colonPosInLine = line.lastIndexOf(':', col - 1);
                if (colonPosInLine !== -1) {
                    const textBetween = line.substring(colonPosInLine + 1, col);
                    if (/^\s*$/.test(textBetween)) {
                        const afterColonAbs = lineInfo.lineStart + colonPosInLine + 1;
                        const lineEnd = lineInfo.lineStart + line.length;
                        const leadingWhitespace = line.match(/^\s*/)[0];
                        const afterText = value.substring(start, lineEnd); // остаток строки после курсора

                        // Заменяем хвост строки после двоеточия
                        this.setSelectionRange(afterColonAbs, lineEnd);
                        const newText = '\n' + leadingWhitespace + indent + afterText;
                        insertTextAtSelection(newText);

                        const newCursorPos = afterColonAbs + 1 + leadingWhitespace.length + indent.length;
                        this.setSelectionRange(newCursorPos, newCursorPos);
                        return;
                    }
                }

                // Случай 3: обычный Enter (сохраняем отступ предыдущей строки)
                const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];
                const newText = '\n' + leadingWhitespace;
                insertTextAtSelection(newText);
                return;
            }

            // --- Автозакрытие скобок и кавычек ---
            if (event.key.length === 1 && (openBrackets.includes(event.key) || closeBrackets.includes(event.key))) {
                event.preventDefault();

                const cursorPos = start;
                const nextChar = value[cursorPos] || '';

                if (openBrackets.includes(event.key)) {
                    if (start !== end) {
                        // Выделенный текст оборачиваем в скобки
                        const selected = value.substring(start, end);
                        const newText = event.key + selected + bracketPairs[event.key];
                        insertTextAtSelection(newText);
                        this.setSelectionRange(start + 1, end + 1);
                    } else {
                        // Вставляем пару, курсор между ними
                        const newText = event.key + bracketPairs[event.key];
                        insertTextAtSelection(newText);
                        this.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    }
                } else if (closeBrackets.includes(event.key)) {
                    if (nextChar === event.key) {
                        // Перепрыгиваем через уже существующий закрывающий символ
                        this.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    } else {
                        // Просто вставляем закрывающий символ
                        insertTextAtSelection(event.key);
                    }
                }
                return;
            }
        });

        console.log('Toadbin tab script loaded. Tab, Shift+Tab, Auto-closing brackets, Enter with indentation (including after colon), and Ctrl+L now supported. Undo/redo works via execCommand.');
    });
})();