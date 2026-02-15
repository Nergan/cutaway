// copy.js – универсальное копирование для всех устройств

(function() {
    // --- Вспомогательные функции ---

    // Функция копирования с использованием Clipboard API или fallback
    function copyToClipboard(text) {
        return new Promise((resolve, reject) => {
            // Пробуем современный Clipboard API (работает в HTTPS и localhost)
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text)
                    .then(resolve)
                    .catch(() => {
                        // Если API не сработал, используем fallback
                        fallbackCopy(text) ? resolve() : reject();
                    });
            } else {
                // Для HTTP или старых браузеров – fallback
                fallbackCopy(text) ? resolve() : reject();
            }
        });
    }

    // Улучшенный fallback-метод с созданием textarea
    function fallbackCopy(text) {
        try {
            const textArea = document.createElement('textarea');
            textArea.value = text;

            // Делаем элемент видимым (но прозрачным) и помещаем в область видимости
            textArea.style.position = 'fixed';
            textArea.style.left = '0';
            textArea.style.top = '0';
            textArea.style.width = '2em';
            textArea.style.height = '2em';
            textArea.style.padding = '0';
            textArea.style.border = 'none';
            textArea.style.outline = 'none';
            textArea.style.boxShadow = 'none';
            textArea.style.background = 'transparent';
            textArea.style.opacity = '0';
            textArea.style.pointerEvents = 'none';
            textArea.style.zIndex = '-1000';

            document.body.appendChild(textArea);

            // Фокусируем элемент
            textArea.focus();

            // Особое выделение для iOS
            if (/ipad|iphone|ipod/i.test(navigator.userAgent)) {
                const range = document.createRange();
                range.selectNodeContents(textArea);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                textArea.setSelectionRange(0, textArea.value.length);
            } else {
                textArea.select();
            }

            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);
            return successful;
        } catch (err) {
            console.error('Fallback copy failed:', err);
            return false;
        }
    }

    // Показ уведомления на мобильных устройствах
    function showMobileNotification(message) {
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
    }

    // --- Обработчик для кнопки копирования кода (глобальный, без async/await) ---
    function handleCopyCode(event) {
        event.preventDefault();
        event.stopPropagation();

        const copyButton = document.getElementById('copyCodeButton');
        const codeInput = document.getElementById('codeInput');
        if (!copyButton || !codeInput) return;

        const codeToCopy = codeInput.value;
        const originalHTML = copyButton.innerHTML;
        const originalTitle = copyButton.getAttribute('title') || '';
        const originalClass = copyButton.className;

        copyToClipboard(codeToCopy)
            .then(() => {
                // Успех
                if ('ontouchstart' in window) {
                    showMobileNotification('Code copied to clipboard!');
                }

                copyButton.innerHTML = '<i class="bi bi-check2"></i>';
                copyButton.setAttribute('title', 'Code copied!');
                copyButton.className = originalClass + ' copied';

                setTimeout(() => {
                    copyButton.innerHTML = originalHTML;
                    copyButton.setAttribute('title', originalTitle);
                    copyButton.className = originalClass;
                }, 2000);
            })
            .catch((err) => {
                console.error('Copy code error:', err);

                if ('ontouchstart' in window) {
                    showMobileNotification('Copy failed! Try tapping and holding.');
                }

                copyButton.innerHTML = '<i class="bi bi-x"></i>';
                copyButton.setAttribute('title', 'Copy failed');

                setTimeout(() => {
                    copyButton.innerHTML = originalHTML;
                    copyButton.setAttribute('title', originalTitle);
                }, 2000);
            });
    }

    // --- Обработчик для элементов с классом .copyable-text (ID кода) ---
    function setupCopyableTextElements() {
        document.querySelectorAll('.copyable-text').forEach(element => {
            // Удаляем старые обработчики, чтобы избежать дублирования (если скрипт загружается повторно)
            element.removeEventListener('click', handleCopyableClick);
            element.removeEventListener('touchstart', handleCopyableTouch);
            element.addEventListener('click', handleCopyableClick);
            element.addEventListener('touchstart', handleCopyableTouch, { passive: false });
            element.addEventListener('touchend', (e) => e.preventDefault());
        });
    }

    // Отдельные функции для .copyable-text, чтобы можно было удалять обработчики
    function handleCopyableClick(event) {
        event.preventDefault();
        event.stopPropagation();
        performCopyableCopy(event.currentTarget);
    }

    function handleCopyableTouch(event) {
        event.preventDefault();
        event.stopPropagation();
        performCopyableCopy(event.currentTarget);
    }

    function performCopyableCopy(element) {
        const textToCopy = element.getAttribute('data-clipboard-text') || element.textContent;
        const originalText = element.textContent;
        const originalColor = element.style.color;

        copyToClipboard(textToCopy)
            .then(() => {
                if ('ontouchstart' in window) {
                    showMobileNotification('Copied to clipboard!');
                }

                element.textContent = 'Copied!';
                element.style.color = '#28a745';

                setTimeout(() => {
                    element.textContent = originalText;
                    element.style.color = originalColor;
                }, 2000);
            })
            .catch((err) => {
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
            });
    }

    // --- Добавление мобильных стилей (если ещё не добавлены) ---
    function addMobileStyles() {
        if (document.getElementById('copy-mobile-styles')) return;

        const style = document.createElement('style');
        style.id = 'copy-mobile-styles';
        style.textContent = `
            .copyable-text, #copyCodeButton {
                -webkit-tap-highlight-color: rgba(0, 255, 0, 0.3);
                tap-highlight-color: rgba(0, 255, 0, 0.3);
                user-select: none;
                cursor: pointer;
            }

            @media (max-width: 768px) {
                .copyable-text, #copyCodeButton {
                    min-height: 48px !important;
                    min-width: 48px !important;
                    padding: 12px !important;
                }

                #copyCodeButton {
                    position: relative !important;
                    z-index: 100 !important;
                    background: rgba(40, 167, 69, 0.9) !important;
                    border: 2px solid white !important;
                    border-radius: 50% !important;
                    width: 60px !important;
                    height: 60px !important;
                    font-size: 1.5rem !important;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important;
                }

                .header .d-flex {
                    position: relative;
                    padding-right: 70px !important;
                }

                #copyCodeButton {
                    position: absolute !important;
                    top: 50% !important;
                    right: 0 !important;
                    transform: translateY(-50%) !important;
                }
            }

            @media (max-width: 576px) {
                #copyCodeButton {
                    width: 50px !important;
                    height: 50px !important;
                    font-size: 1.2rem !important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // --- Инициализация после загрузки DOM ---
    document.addEventListener('DOMContentLoaded', function() {
        // Назначаем обработчик на кнопку копирования
        const copyButton = document.getElementById('copyCodeButton');
        if (copyButton) {
            copyButton.addEventListener('click', handleCopyCode);
            copyButton.addEventListener('touchstart', handleCopyCode, { passive: false });
            copyButton.addEventListener('touchend', (e) => e.preventDefault());
        }

        // Настраиваем элементы .copyable-text
        setupCopyableTextElements();

        // Добавляем стили
        addMobileStyles();

        // Специальная обработка для iOS (контекстное меню на textarea)
        if (/ipad|iphone|ipod/i.test(navigator.userAgent)) {
            const codeInput = document.getElementById('codeInput');
            if (codeInput) {
                codeInput.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    // Вызываем копирование через глобальную функцию
                    if (copyButton) {
                        handleCopyCode(e);
                    } else {
                        // Если кнопки нет, копируем напрямую
                        copyToClipboard(codeInput.value)
                            .then(() => showMobileNotification('Code copied!'))
                            .catch(() => showMobileNotification('Copy failed'));
                    }
                });
            }

            // Дополнительно: разрешаем касания для активации жестов
            document.addEventListener('touchstart', function() {}, { passive: true });
        }

        // Наблюдаем за появлением новых .copyable-text (если DOM динамически меняется)
        const observer = new MutationObserver(() => {
            setupCopyableTextElements();
        });
        observer.observe(document.body, { childList: true, subtree: true });
    });

})();