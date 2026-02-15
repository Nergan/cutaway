// copy.js – ультра-надёжная версия для всех устройств
(function() {
    'use strict';

    console.log('[Copy] Script loaded');

    // ==== КРИТИЧНЫЕ СТИЛИ, ЕСЛИ CSS НЕ ЗАГРУЗИЛСЯ (дублируем здесь) ====
    function ensureMobileStyles() {
        if (document.getElementById('copy-fallback-styles')) return;
        const style = document.createElement('style');
        style.id = 'copy-fallback-styles';
        style.textContent = `
            /* Эти стили будут добавлены даже если основной CSS не загрузился */
            @media (max-width: 768px) {
                #copyCodeButton {
                    position: absolute !important;
                    top: 50% !important;
                    right: 0 !important;
                    transform: translateY(-50%) !important;
                    z-index: 100 !important;
                    background: #28a745 !important;
                    border: 2px solid white !important;
                    border-radius: 50% !important;
                    width: 60px !important;
                    height: 60px !important;
                    display: flex !important;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;
                }
                .header .d-flex {
                    padding-right: 70px !important;
                    position: relative !important;
                }
            }
        `;
        document.head.appendChild(style);
        console.log('[Copy] Fallback styles added');
    }

    // ==== ФУНКЦИЯ КОПИРОВАНИЯ (СИНХРОННАЯ) ====
    function copyTextToClipboard(text) {
        // Пытаемся использовать современный Clipboard API (только если страница в безопасном контексте)
        if (window.isSecureContext && navigator.clipboard) {
            try {
                // Вызов асинхронный, но мы сразу возвращаем Promise, а в обработчике будем использовать .then
                return navigator.clipboard.writeText(text).then(() => {
                    console.log('[Copy] Clipboard API success');
                    return true;
                }).catch(err => {
                    console.warn('[Copy] Clipboard API failed, trying fallback', err);
                    return fallbackCopy(text);
                });
            } catch (e) {
                console.warn('[Copy] Clipboard API exception', e);
                return fallbackCopy(text);
            }
        } else {
            console.log('[Copy] Using fallback (no secure context or no clipboard API)');
            return fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        try {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '0';
            textArea.style.top = '0';
            textArea.style.width = '2em';
            textArea.style.height = '2em';
            textArea.style.opacity = '0';
            textArea.style.pointerEvents = 'none';
            textArea.style.zIndex = '-1000';
            document.body.appendChild(textArea);

            textArea.focus();
            textArea.select();

            // Для iOS
            if (/ipad|iphone|ipod/i.test(navigator.userAgent)) {
                textArea.setSelectionRange(0, textArea.value.length);
            }

            const success = document.execCommand('copy');
            document.body.removeChild(textArea);
            console.log('[Copy] Fallback result:', success);
            return success ? Promise.resolve(true) : Promise.reject('execCommand failed');
        } catch (err) {
            console.error('[Copy] Fallback error:', err);
            return Promise.reject(err);
        }
    }

    // ==== УВЕДОМЛЕНИЕ ====
    function showNotification(message, isSuccess = true) {
        let notif = document.getElementById('copy-notification');
        if (!notif) {
            notif = document.createElement('div');
            notif.id = 'copy-notification';
            notif.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: ${isSuccess ? '#28a745' : '#dc3545'};
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                z-index: 100000;
                font-size: 14px;
                text-align: center;
                max-width: 80%;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.2);
                opacity: 0;
                transition: opacity 0.2s;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            `;
            document.body.appendChild(notif);
        } else {
            notif.style.background = isSuccess ? '#28a745' : '#dc3545';
        }
        notif.textContent = message;
        notif.style.opacity = '1';
        setTimeout(() => {
            notif.style.opacity = '0';
        }, 2000);
    }

    // ==== ОБРАБОТЧИК ДЛЯ КНОПКИ КОПИРОВАНИЯ ====
    function onCopyButtonClick(event) {
        event.preventDefault();
        event.stopPropagation();

        const btn = document.getElementById('copyCodeButton');
        const codeInput = document.getElementById('codeInput');
        if (!btn || !codeInput) {
            console.warn('[Copy] Button or textarea not found');
            return;
        }

        const code = codeInput.value;
        console.log('[Copy] Button clicked, code length:', code.length);

        // Сохраняем оригинальное содержимое кнопки
        const originalHTML = btn.innerHTML;
        const originalTitle = btn.title;

        // Пытаемся скопировать
        copyTextToClipboard(code).then(success => {
            if (success) {
                showNotification('Code copied!', true);
                btn.innerHTML = '<i class="bi bi-check2"></i>';
                btn.title = 'Copied!';
                btn.classList.add('copied');
            } else {
                showNotification('Copy failed', false);
                btn.innerHTML = '<i class="bi bi-x"></i>';
                btn.title = 'Failed';
            }
        }).catch(err => {
            console.error('[Copy] Copy error:', err);
            showNotification('Copy failed', false);
            btn.innerHTML = '<i class="bi bi-x"></i>';
            btn.title = 'Failed';
        }).finally(() => {
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.title = originalTitle;
                btn.classList.remove('copied');
            }, 2000);
        });
    }

    // ==== ОБРАБОТЧИК ДЛЯ ID (copyable-text) ====
    function onCopyIdClick(event) {
        event.preventDefault();
        event.stopPropagation();

        const el = event.currentTarget;
        const text = el.dataset.clipboardText || el.textContent;
        const originalText = el.textContent;
        const originalColor = el.style.color;

        copyTextToClipboard(text).then(success => {
            if (success) {
                showNotification('ID copied!', true);
                el.textContent = 'Copied!';
                el.style.color = '#28a745';
            } else {
                showNotification('Copy failed', false);
                el.textContent = 'Error';
                el.style.color = '#dc3545';
            }
        }).catch(() => {
            showNotification('Copy failed', false);
            el.textContent = 'Error';
            el.style.color = '#dc3545';
        }).finally(() => {
            setTimeout(() => {
                el.textContent = originalText;
                el.style.color = originalColor;
            }, 2000);
        });
    }

    // ==== ИНИЦИАЛИЗАЦИЯ ====
    document.addEventListener('DOMContentLoaded', function() {
        console.log('[Copy] DOM ready');

        // Добавляем страховочные стили
        ensureMobileStyles();

        // Кнопка копирования кода
        const copyBtn = document.getElementById('copyCodeButton');
        if (copyBtn) {
            copyBtn.addEventListener('click', onCopyButtonClick);
            // На мобильных touch тоже срабатывает, но click достаточно
            console.log('[Copy] Copy button found, handler attached');
        } else {
            console.log('[Copy] No copy button on this page');
        }

        // Элементы ID
        const idElements = document.querySelectorAll('.copyable-text');
        if (idElements.length) {
            idElements.forEach(el => {
                el.addEventListener('click', onCopyIdClick);
            });
            console.log('[Copy] Attached to', idElements.length, 'ID elements');
        }

        // Для iOS: добавим копирование по долгому нажатию на textarea
        if (/ipad|iphone|ipod/i.test(navigator.userAgent)) {
            const codeInput = document.getElementById('codeInput');
            if (codeInput) {
                codeInput.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    if (copyBtn) {
                        onCopyButtonClick(e);
                    } else {
                        // Если кнопки нет, копируем напрямую
                        copyTextToClipboard(codeInput.value).then(() => {
                            showNotification('Code copied!', true);
                        }).catch(() => {
                            showNotification('Copy failed', false);
                        });
                    }
                });
            }
        }

        console.log('[Copy] Init complete, secure context:', window.isSecureContext);
    });
})();