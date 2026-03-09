(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, codekeys.js will not work');
            return;
        }

        const INDENT = '    '; // 4 spaces
        const OPEN_BRACKETS = ['(', '[', '{', '<', "'", '"', '`'];
        const CLOSE_BRACKETS = [')', ']', '}', '>', "'", '"', '`'];
        const BRACKET_PAIRS = {
            '(': ')',
            '[': ']',
            '{': '}',
            '<': '>',
            "'": "'",
            '"': '"',
            '`': '`'
        };

        /**
         * Get information about the line at a given position.
         * @param {string} text - The full textarea content.
         * @param {number} pos - The cursor position.
         * @returns {Object} Line info: index, column, line start index, line text.
         */
        const getLineInfo = (text, pos) => {
            const lines = text.split('\n');
            const starts = [];
            let currentPos = 0;
            for (let i = 0; i < lines.length; i++) {
                starts[i] = currentPos;
                currentPos += lines[i].length + 1;
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
            // Fallback to last line
            const lastLineIndex = lines.length - 1;
            return {
                lineIndex: lastLineIndex,
                col: lines[lastLineIndex].length,
                lineStart: starts[lastLineIndex],
                line: lines[lastLineIndex]
            };
        };

        /**
         * Insert text at the current cursor/selection position.
         * Uses execCommand if available, otherwise manual insertion.
         * @param {string} text - Text to insert.
         */
        const insertTextAtSelection = (text) => {
            if (document.execCommand('insertText', false, text)) {
                return true;
            } else {
                const start = codeInput.selectionStart;
                const end = codeInput.selectionEnd;
                const value = codeInput.value;
                codeInput.value = value.substring(0, start) + text + value.substring(end);
                codeInput.selectionStart = codeInput.selectionEnd = start + text.length;
                codeInput.dispatchEvent(new Event('input', { bubbles: true }));
                return false;
            }
        };

        codeInput.addEventListener('keydown', (event) => {
            const start = codeInput.selectionStart;
            const end = codeInput.selectionEnd;
            const value = codeInput.value;

            // Ctrl+L: select current line
            if (event.ctrlKey && event.key === 'l') {
                event.preventDefault();
                const lineInfo = getLineInfo(value, start);
                const lineStart = lineInfo.lineStart;
                const lineEnd = lineStart + lineInfo.line.length;
                codeInput.selectionStart = lineStart;
                codeInput.selectionEnd = lineEnd;
                return;
            }

            // Tab / Shift+Tab handling
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault();

                if (event.shiftKey) {
                    // Shift+Tab: remove one indent level from selected lines or current line
                    if (start === end) {
                        const lineInfo = getLineInfo(value, start);
                        const line = lineInfo.line;
                        if (line.startsWith(INDENT)) {
                            const newLine = line.substring(INDENT.length);
                            const newStart = lineInfo.lineStart;
                            const newEnd = lineInfo.lineStart + line.length;
                            codeInput.setSelectionRange(newStart, newEnd);
                            insertTextAtSelection(newLine);
                            const newCursor = lineInfo.lineStart + Math.max(0, start - lineInfo.lineStart - INDENT.length);
                            codeInput.setSelectionRange(newCursor, newCursor);
                        }
                        return;
                    }

                    // Multi-line selection
                    const lines = value.split('\n');
                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1);
                    const firstLine = startInfo.lineIndex;
                    const lastLine = endInfo.lineIndex;

                    const originalLines = lines.slice(firstLine, lastLine + 1);
                    const modifiedLines = originalLines.map(line =>
                        line.startsWith(INDENT) ? line.substring(INDENT.length) : line
                    );

                    const before = value.substring(0, startInfo.lineStart);
                    const after = value.substring(endInfo.lineStart + endInfo.line.length + (lastLine < lines.length - 1 ? 1 : 0));
                    const newText = modifiedLines.join('\n');
                    const rangeStart = startInfo.lineStart;
                    const rangeEnd = endInfo.lineStart + endInfo.line.length + (lastLine - firstLine);
                    codeInput.setSelectionRange(rangeStart, rangeEnd);
                    insertTextAtSelection(newText);
                    codeInput.setSelectionRange(rangeStart, rangeStart + newText.length);
                } else {
                    // Tab: add indent to selected lines or insert at cursor
                    if (start === end) {
                        insertTextAtSelection(INDENT);
                        return;
                    }

                    // Multi-line selection
                    const lines = value.split('\n');
                    const startInfo = getLineInfo(value, start);
                    const endInfo = getLineInfo(value, end - 1);
                    const firstLine = startInfo.lineIndex;
                    const lastLine = endInfo.lineIndex;

                    const originalLines = lines.slice(firstLine, lastLine + 1);
                    const modifiedLines = originalLines.map(line => INDENT + line);

                    const before = value.substring(0, startInfo.lineStart);
                    const after = value.substring(endInfo.lineStart + endInfo.line.length + (lastLine < lines.length - 1 ? 1 : 0));
                    const newText = modifiedLines.join('\n');
                    const rangeStart = startInfo.lineStart;
                    const rangeEnd = endInfo.lineStart + endInfo.line.length + (lastLine - firstLine);
                    codeInput.setSelectionRange(rangeStart, rangeEnd);
                    insertTextAtSelection(newText);
                    codeInput.setSelectionRange(rangeStart, rangeStart + newText.length);
                }
                return;
            }

            // Enter key handling with auto-indent and bracket expansion
            if (event.key === 'Enter') {
                event.preventDefault();

                const before = value.substring(0, start);
                const after = value.substring(end);
                const prevChar = before.slice(-1);
                const nextChar = after[0] || '';

                // Case: cursor between opening and closing brackets, e.g., {|}
                if (OPEN_BRACKETS.includes(prevChar) && CLOSE_BRACKETS.includes(nextChar) && BRACKET_PAIRS[prevChar] === nextChar) {
                    const openPos = start - 1;
                    const closePos = start;
                    const lineInfo = getLineInfo(value, openPos);
                    const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];

                    // Replace both brackets with a multi-line block
                    codeInput.setSelectionRange(openPos, closePos + 1);
                    const newText = prevChar + '\n' + leadingWhitespace + INDENT + '\n' + leadingWhitespace + nextChar;
                    insertTextAtSelection(newText);

                    // Place cursor after the opening bracket and newline+indent
                    const newCursorPos = openPos + 1 + 1 + leadingWhitespace.length + INDENT.length; // 1 for openChar, 1 for '\n'
                    codeInput.setSelectionRange(newCursorPos, newCursorPos);
                    return;
                }

                // Case: colon in the current line before cursor with only whitespace between
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
                        const afterText = value.substring(start, lineEnd);

                        // Replace the rest of the line after colon
                        codeInput.setSelectionRange(afterColonAbs, lineEnd);
                        const newText = '\n' + leadingWhitespace + INDENT + afterText;
                        insertTextAtSelection(newText);

                        const newCursorPos = afterColonAbs + 1 + leadingWhitespace.length + INDENT.length;
                        codeInput.setSelectionRange(newCursorPos, newCursorPos);
                        return;
                    }
                }

                // Default Enter: insert newline and copy indentation from previous line
                const leadingWhitespace = lineInfo.line.match(/^\s*/)[0];
                const newText = '\n' + leadingWhitespace;
                insertTextAtSelection(newText);
                // Cursor is automatically placed after the inserted text (execCommand does that)
                return;
            }

            // Auto-closing brackets and quotes
            if (event.key.length === 1 && (OPEN_BRACKETS.includes(event.key) || CLOSE_BRACKETS.includes(event.key))) {
                event.preventDefault();

                const cursorPos = start;
                const nextChar = value[cursorPos] || '';

                if (OPEN_BRACKETS.includes(event.key)) {
                    if (start !== end) {
                        const selected = value.substring(start, end);
                        const newText = event.key + selected + BRACKET_PAIRS[event.key];
                        insertTextAtSelection(newText);
                        codeInput.setSelectionRange(start + 1, end + 1);
                    } else {
                        const newText = event.key + BRACKET_PAIRS[event.key];
                        insertTextAtSelection(newText);
                        codeInput.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    }
                } else if (CLOSE_BRACKETS.includes(event.key)) {
                    if (nextChar === event.key) {
                        codeInput.setSelectionRange(cursorPos + 1, cursorPos + 1);
                    } else {
                        insertTextAtSelection(event.key);
                    }
                }
                return;
            }
        });

        console.log('Toadbin codekeys loaded: Tab/Shift+Tab, Enter with indentation, auto-closing brackets, Ctrl+L.');
    });
})();