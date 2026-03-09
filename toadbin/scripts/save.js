(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, save.js will not work');
            return;
        }

        let isProcessing = false;

        /**
         * Show a notification message.
         * @param {string} message - Message to display.
         * @param {number} duration - Display duration in ms.
         */
        const showNotification = (message, duration = 5000) => {
            let notification = document.getElementById('notification');
            if (!notification) {
                notification = document.createElement('div');
                notification.id = 'notification';
                notification.className = 'notification';
                document.body.appendChild(notification);
            }

            if (notification.timeoutId) {
                clearTimeout(notification.timeoutId);
            }

            notification.textContent = message;
            setTimeout(() => {
                notification.classList.add('show');
            }, 10);

            notification.timeoutId = setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.remove();
                    }
                }, 300);
            }, duration);
        };

        /**
         * Fetch all existing code IDs from the server.
         * @returns {Promise<string[]>}
         */
        const getExistingIds = async () => {
            try {
                const response = await fetch('./api/existing-ids');
                if (!response.ok) throw new Error('Failed to fetch existing IDs');
                return await response.json();
            } catch (error) {
                console.error('Error fetching existing IDs:', error);
                return [];
            }
        };

        /**
         * Generate a random UUID v4 (not cryptographically secure).
         * @returns {string}
         */
        const generateUUIDv4 = () => {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        };

        /**
         * Generate a unique ID not present in existingIds.
         * @param {string[]} existingIds - List of existing IDs.
         * @returns {string}
         * @throws Will throw if unable to generate unique ID after max attempts.
         */
        const generateUniqueId = (existingIds) => {
            const maxAttempts = 100;
            for (let attempts = 0; attempts < maxAttempts; attempts++) {
                const newId = generateUUIDv4();
                if (!existingIds.includes(newId)) {
                    return newId;
                }
            }
            throw new Error('Failed to generate unique ID after 100 attempts');
        };

        /**
         * Save the current code to the server.
         */
        const saveCode = async () => {
            if (isProcessing) return;

            const code = codeInput.value.trim();
            if (!code) {
                showNotification('Please enter some code before saving.', 3000);
                return;
            }

            isProcessing = true;

            try {
                const existingIds = await getExistingIds();
                const newId = generateUniqueId(existingIds);

                const response = await fetch('./api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: newId, code: code })
                });

                if (response.ok) {
                    window.location.href = `/toadbin/${newId}`;
                } else {
                    throw new Error('Failed to save code');
                }
            } catch (error) {
                console.error('Error saving code:', error);
                showNotification('Sorry, database is busy :(');
            } finally {
                isProcessing = false;
            }
        };

        // Prevent default browser save (Ctrl+S) when focused on textarea
        window.addEventListener('keydown', (event) => {
            const isCtrlS = (event.ctrlKey || event.metaKey) &&
                (event.code === 'KeyS' || event.key === 's' || event.key === 'ы');
            if (isCtrlS && document.activeElement === codeInput) {
                event.preventDefault();
            }
        });

        // Trigger save on Ctrl+S
        codeInput.addEventListener('keydown', (event) => {
            const isCtrlS = (event.ctrlKey || event.metaKey) &&
                (event.code === 'KeyS' || event.key === 's' || event.key === 'ы');
            if (isCtrlS) {
                saveCode();
            }
        });

        console.log('Toadbin save script loaded. Press Ctrl+S (any layout) to save your code.');
    });
})();