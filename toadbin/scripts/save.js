// toadbin/scripts/save.js
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, save.js will not work');
            return;
        }

        let isProcessing = false;

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

        async function saveCode() {
            if (isProcessing) return;
            
            const code = codeInput.value.trim();
            if (!code) {
                alert('Please enter some code before saving.');
                return;
            }
            
            isProcessing = true;
            
            try {
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
                isProcessing = false;
            }
        }

        // Глобальный обработчик для предотвращения стандартного сохранения страницы
        window.addEventListener('keydown', function(event) {
            // Проверяем Ctrl+S или Cmd+S НЕЗАВИСИМО от раскладки
            const isCtrlS = (event.ctrlKey || event.metaKey) && 
                           (event.code === 'KeyS' || event.key === 's' || event.key === 'ы');
            
            // Если это Ctrl+S и фокус на textarea, блокируем стандартное поведение
            if (isCtrlS && document.activeElement === codeInput) {
                event.preventDefault();
            }
        });

        // Обработчик на textarea для вызова нашей функции сохранения
        codeInput.addEventListener('keydown', function(event) {
            // Проверяем Ctrl+S или Cmd+S НЕЗАВИСИМО от раскладки
            const isCtrlS = (event.ctrlKey || event.metaKey) && 
                           (event.code === 'KeyS' || event.key === 's' || event.key === 'ы');
            
            if (isCtrlS) {
                // Сохраняем код
                saveCode();
            }
        });

        console.log('Toadbin save script loaded. Press Ctrl+S (any layout) to save your code.');
    });
})();