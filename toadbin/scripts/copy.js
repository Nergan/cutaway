(function() {
    'use strict';

    /**
     * Copy text to clipboard using modern API or fallback.
     * @param {string} text - Text to copy.
     * @returns {Promise<void>}
     */
    const copyToClipboard = async (text) => {
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                return;
            } catch (err) {
                // Fallback to legacy method
            }
        }
        // Legacy fallback
        return new Promise((resolve, reject) => {
            if (fallbackCopy(text)) {
                resolve();
            } else {
                reject(new Error('Fallback copy failed'));
            }
        });
    };

    /**
     * Fallback copy method using temporary textarea.
     * @param {string} text - Text to copy.
     * @returns {boolean} Success status.
     */
    const fallbackCopy = (text) => {
        try {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            textArea.style.opacity = '0';
            textArea.style.pointerEvents = 'none';
            textArea.style.zIndex = '-1000';
            document.body.appendChild(textArea);

            // Special handling for iOS
            if (navigator.userAgent.match(/ipad|iphone/i)) {
                const range = document.createRange();
                range.selectNodeContents(textArea);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                textArea.setSelectionRange(0, 999999);
            } else {
                textArea.select();
            }

            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);
            return successful;
        } catch (err) {
            console.error('Fallback copy error:', err);
            return false;
        }
    };

    /**
     * Show a temporary notification on mobile devices.
     * @param {string} message - Message to display.
     */
    const showMobileNotification = (message) => {
        let notification = document.getElementById('mobile-notification');
        if (!notification) {
            notification = document.createElement('div');
            notification.id = 'mobile-notification';
            notification.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                z-index: 9999;
                font-size: 14px;
                text-align: center;
                max-width: 80%;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                opacity: 0;
                transition: opacity 0.3s ease;
            `;
            document.body.appendChild(notification);
        }

        notification.textContent = message;
        notification.style.opacity = '1';

        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.textContent = '';
                }
            }, 300);
        }, 2000);
    };

    // Attach copy handlers to elements with class 'copyable-text'
    document.querySelectorAll('.copyable-text').forEach((element) => {
        const handleCopy = async (event) => {
            event.preventDefault();
            event.stopPropagation();

            const textToCopy = element.getAttribute('data-clipboard-text') || element.textContent;
            const originalText = element.textContent;
            const originalColor = element.style.color;

            try {
                await copyToClipboard(textToCopy);

                if ('ontouchstart' in window) {
                    showMobileNotification('Copied to clipboard!');
                }

                // Visual feedback
                element.textContent = 'Copied!';
                element.style.color = '#28a745';

                setTimeout(() => {
                    element.textContent = originalText;
                    element.style.color = originalColor;
                }, 2000);
            } catch (err) {
                console.error('Copy error:', err);

                if ('ontouchstart' in window) {
                    showMobileNotification('Copy failed! Try tapping and holding.');
                }

                element.textContent = 'Error :(';
                element.style.color = '#dc3545';

                setTimeout(() => {
                    element.textContent = originalText;
                    element.style.color = originalColor;
                }, 2000);
            }
        };

        element.addEventListener('click', handleCopy);
        element.addEventListener('touchstart', handleCopy, { passive: false });
        element.addEventListener('touchend', (e) => e.preventDefault());
    });

    // Handle copy button for the entire code
    const copyCodeButton = document.getElementById('copyCodeButton');
    if (copyCodeButton) {
        const handleCopyCode = async (event) => {
            event.preventDefault();
            event.stopPropagation();

            const codeInput = document.getElementById('codeInput');
            if (!codeInput) return;

            const codeToCopy = codeInput.value;
            const originalHTML = copyCodeButton.innerHTML;
            const originalTitle = copyCodeButton.getAttribute('title');
            const originalClass = copyCodeButton.className;

            try {
                await copyToClipboard(codeToCopy);

                if ('ontouchstart' in window) {
                    showMobileNotification('Code copied to clipboard!');
                }

                copyCodeButton.innerHTML = '<i class="bi bi-check2"></i>';
                copyCodeButton.setAttribute('title', 'Code copied!');
                copyCodeButton.className = originalClass + ' copied';

                setTimeout(() => {
                    copyCodeButton.innerHTML = originalHTML;
                    copyCodeButton.setAttribute('title', originalTitle);
                    copyCodeButton.className = originalClass;
                }, 2000);
            } catch (err) {
                console.error('Copy code error:', err);

                if ('ontouchstart' in window) {
                    showMobileNotification('Copy failed! Try tapping and holding.');
                }

                copyCodeButton.innerHTML = '<i class="bi bi-x"></i>';
                copyCodeButton.setAttribute('title', 'Copy failed');

                setTimeout(() => {
                    copyCodeButton.innerHTML = originalHTML;
                    copyCodeButton.setAttribute('title', originalTitle);
                }, 2000);
            }
        };

        copyCodeButton.addEventListener('click', handleCopyCode);
        copyCodeButton.addEventListener('touchstart', handleCopyCode, { passive: false });
        copyCodeButton.addEventListener('touchend', (e) => e.preventDefault());
    }

    // Additional iOS handling
    if (navigator.userAgent.match(/ipad|iphone|ipod/i)) {
        document.addEventListener('touchstart', () => {}, { passive: true });

        const codeInput = document.getElementById('codeInput');
        if (codeInput) {
            codeInput.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                // Could trigger custom copy here, but for now just prevent default
            });
        }
    }
})();