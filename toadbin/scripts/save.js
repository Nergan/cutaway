(function() {
    'use strict';

    // Wait for DOM to be ready
    document.addEventListener('DOMContentLoaded', () => {
        // DOM elements
        const codeInput = document.getElementById('codeInput');
        const saveButton = document.getElementById('saveCodeButton');

        // Exit if the main textarea is missing
        if (!codeInput) {
            console.warn('codeInput not found, save.js will not work');
            return;
        }

        // State
        let isProcessing = false;
        let notificationTimeoutId = null;

        // Constants
        const NOTIFICATION_DURATION = 5000;
        const SHORT_NOTIFICATION_DURATION = 3000;
        const ERROR_RESET_DELAY = 2000;

        // ----------------------------------------------------------------------
        // Helper functions
        // ----------------------------------------------------------------------

        /**
         * Shows a notification message.
         * @param {string} message - Message to display
         * @param {number} [duration=5000] - How long to show the message (ms)
         */
        function showNotification(message, duration = NOTIFICATION_DURATION) {
            // Get or create notification element
            let notification = document.getElementById('notification');
            if (!notification) {
                notification = document.createElement('div');
                notification.id = 'notification';
                notification.className = 'notification';
                document.body.appendChild(notification);
            }

            // Clear previous timeout
            if (notificationTimeoutId) {
                clearTimeout(notificationTimeoutId);
                notificationTimeoutId = null;
            }

            // Set message and show with a tiny delay for CSS transition
            notification.textContent = message;
            setTimeout(() => notification.classList.add('show'), 10);

            // Schedule hide and removal
            notificationTimeoutId = setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.remove();
                    }
                    notificationTimeoutId = null;
                }, 300);
            }, duration);
        }

        /**
         * Generates a random UUID v4.
         * Falls back to a manual generator if crypto.randomUUID is not available.
         * @returns {string}
         */
        function generateUUID() {
            if (typeof crypto !== 'undefined' && crypto.randomUUID) {
                return crypto.randomUUID();
            }
            // Fallback for older browsers
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        }

        // ----------------------------------------------------------------------
        // Save logic
        // ----------------------------------------------------------------------

        /**
         * Saves the current code to the server.
         * @returns {Promise<boolean>} True if successful (will redirect), false on error.
         */
        async function saveCode() {
            if (isProcessing) return false;

            const code = codeInput.value.trim();
            if (!code) {
                showNotification('please enter some code before saving :^', SHORT_NOTIFICATION_DURATION);
                return false;
            }

            isProcessing = true;
            console.log('saving code...');

            try {
                // Generate a UUID locally, serving as a proposal to the server
                const newId = generateUUID();

                const response = await fetch('./api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: newId, code: code })
                });

                if (response.ok) {
                    // Always use the ID dictated by the server's response.
                    // This handles deduplication by redirecting to an existing ID if one was found!
                    const data = await response.json();
                    window.location.href = `/toadbin/${data.id}`;
                    return true;
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
        }

        // ----------------------------------------------------------------------
        // Button state management
        // ----------------------------------------------------------------------

        /**
         * Temporarily sets the save button to a loading state.
         * @param {HTMLElement} button
         * @returns {Function} A function to restore the button to its original state.
         */
        function setButtonLoading(button) {
            const originalHTML = button.innerHTML;
            const originalTitle = button.getAttribute('title') || '';
            const originalClass = button.className;

            button.innerHTML = '<i class="bi bi-arrow-repeat spin"></i>';
            button.setAttribute('title', 'Saving...');
            button.disabled = true;

            return function restoreButton() {
                button.innerHTML = originalHTML;
                button.setAttribute('title', originalTitle);
                button.className = originalClass;
                button.disabled = false;
            };
        }

        /**
         * Sets the button to an error state, then restores it after a delay.
         * @param {HTMLElement} button
         * @param {Function} restoreFn - Function that restores the button to original state.
         */
        function showButtonError(button, restoreFn) {
            button.innerHTML = '<i class="bi bi-x"></i>';
            button.setAttribute('title', 'Save failed');
            button.className = button.className + ' error';

            setTimeout(restoreFn, ERROR_RESET_DELAY);
        }

        // ----------------------------------------------------------------------
        // Event handlers
        // ----------------------------------------------------------------------

        /**
         * Handles the save button click.
         */
        async function handleSaveClick(event) {
            event.preventDefault();

            // Prevent multiple clicks while processing
            if (isProcessing) return;

            // Early exit if code is empty – avoids loading animation
            if (!codeInput.value.trim()) {
                showNotification('please enter some code before saving :^', SHORT_NOTIFICATION_DURATION);
                return;
            }

            // Store original button state and set loading
            const restoreButton = setButtonLoading(saveButton);

            // Attempt to save
            const success = await saveCode();

            if (!success) {
                // Show error state, then restore after a delay
                showButtonError(saveButton, restoreButton);
            }
            // If success, the page will redirect, so no need to restore
        }

        /**
         * Handles keyboard shortcuts (Ctrl+S / Cmd+S).
         */
        function handleKeyDown(event) {
            const isCtrlS = (event.ctrlKey || event.metaKey) &&
                (event.code === 'KeyS' || event.key === 's' || event.key === 'ы');

            if (!isCtrlS) return;

            // Prevent the browser's native save dialog universally
            event.preventDefault();

            // Programmatically click the save button to trigger the animation and logic uniformly
            if (saveButton) {
                saveButton.click();
            }
        }

        // ----------------------------------------------------------------------
        // Event listeners
        // ----------------------------------------------------------------------

        // Global keydown listener for Ctrl+S (both preventDefault and trigger)
        window.addEventListener('keydown', handleKeyDown);

        // Save button click
        if (saveButton) {
            saveButton.addEventListener('click', handleSaveClick);
        }

        console.log('Toadbin save script loaded. Press Ctrl+S (any layout) to save your code.');
    });
})();