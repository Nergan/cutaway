// toadbin/scripts/save.js
(function() {
    'use strict';

    // Функция сохранения, доступная глобально (вызывается из CodeMirror extraKeys и из обработчика)
    window.saveCode = async function() {
        let code = '';
        if (window.codeMirrorEditor) {
            code = window.codeMirrorEditor.getValue().trim();
        } else {
            const codeInput = document.getElementById('codeInput');
            if (codeInput) {
                code = codeInput.value.trim();
            } else {
                console.warn('No code input found');
                return;
            }
        }

        if (!code) {
            alert('Please enter some code before saving.');
            return;
        }

        if (window.isProcessing) return;
        window.isProcessing = true;

        try {
            async function getExistingIds() {
                try {
                    const response = await fetch('/api/existing-ids');
                    if (!response.ok) throw new Error('Failed to fetch existing IDs');
                    return await response.json();
                } catch (error) {
                    console.error('Error fetching existing IDs:', error);
                    return [];
                }
            }

            function generateUUIDv4() {
                return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    const r = Math.random() * 16 | 0;
                    const v = c === 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                });
            }

            function generateUniqueId(existingIds) {
                let newId;
                const maxAttempts = 100;
                let attempts = 0;

                do {
                    newId = generateUUIDv4();
                    attempts++;
                    if (attempts > maxAttempts) throw new Error('Failed to generate unique ID');
                } while (existingIds.includes(newId));

                return newId;
            }

            const existingIds = await getExistingIds();
            const newId = generateUniqueId(existingIds);

            const response = await fetch('/api/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: newId, code: code})
            });

            if (response.ok) {
                window.location.href = `/toadbin/${newId}`;
            } else {
                throw new Error('Failed to save code');
            }
        } catch (error) {
            console.error('Error saving code:', error);
            alert('An error occurred while saving. Please try again.');
        } finally {
            window.isProcessing = false;
        }
    };

    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput && !window.codeMirrorEditor) {
            console.warn('codeInput not found, save.js will not work');
            return;
        }

        // Глобальный обработчик Ctrl+S (сработает, если фокус не внутри CodeMirror)
        window.addEventListener('keydown', function(event) {
            // Если активен CodeMirror, игнорируем (он сам обработает через extraKeys)
            if (window.codeMirrorEditor && event.target.closest('.CodeMirror')) {
                return;
            }

            const isCtrlS = (event.ctrlKey || event.metaKey) && 
                           (event.code === 'KeyS' || event.key === 's' || event.key === 'ы');
            if (isCtrlS) {
                event.preventDefault();
                window.saveCode();
            }
        });

        console.log('Toadbin save script loaded. Press Ctrl+S (any layout) to save your code.');
    });
})();