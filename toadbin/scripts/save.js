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
         * @returns {Promise<boolean>} - True if successful (will redirect), false on error.
         */
        const saveCode = async () => {
            if (isProcessing) return false;

            const code = codeInput.value.trim();
            if (!code) {
                showNotification('please enter some code before saving :^', 3000);
                return false;
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
                    return true; // Will never actually return due to redirect, but for consistency
                } else {
                    throw new Error('Failed to save code');
                }
            } catch (error) {
                console.error('Error saving code:', error);
                showNotification('Sorry, database is busy :(');
                return false;
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

        // --- Handle save button click with animation ---
        const saveButton = document.getElementById('saveCodeButton');
        if (saveButton) {
            saveButton.addEventListener('click', async (event) => {
                event.preventDefault();

                // Prevent multiple clicks
                if (isProcessing) return;

                // Quick check for empty code to avoid unnecessary loading animation
                if (!codeInput.value.trim()) {
                    showNotification('please enter some code before saving :^', 3000);
                    return;
                }

                // Store original button content
                const originalHTML = saveButton.innerHTML;
                const originalTitle = saveButton.getAttribute('title');
                const originalClass = saveButton.className;

                // Set loading state
                saveButton.innerHTML = '<i class="bi bi-arrow-repeat spin"></i>';
                saveButton.setAttribute('title', 'Saving...');
                saveButton.disabled = true;

                // Perform save
                const success = await saveCode();

                if (!success) {
                    // Show error state briefly
                    saveButton.innerHTML = '<i class="bi bi-x"></i>';
                    saveButton.setAttribute('title', 'Save failed');
                    saveButton.className = originalClass + ' error'; // Use error class instead of copied

                    setTimeout(() => {
                        // Restore original state
                        saveButton.innerHTML = originalHTML;
                        saveButton.setAttribute('title', originalTitle);
                        saveButton.className = originalClass;
                        saveButton.disabled = false;
                    }, 2000);
                }
                // If success, page will redirect, so no need to restore
            });
        }

        console.log('Toadbin save script loaded. Press Ctrl+S (any layout) to save your code.');
    });
})();