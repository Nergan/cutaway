// Улучшенная функция копирования для всех устройств
function copyToClipboard(text) {
  return new Promise((resolve, reject) => {
    // Пробуем современный Clipboard API (работает в Chrome и Safari на iOS 10+)
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text)
        .then(resolve)
        .catch(() => {
          // Если Clipboard API не работает, пробуем старый метод
          fallbackCopy(text) ? resolve() : reject();
        });
    } else {
      // Для HTTP и старых браузеров используем fallback
      fallbackCopy(text) ? resolve() : reject();
    }
  });
}

// Старый надежный метод копирования
function fallbackCopy(text) {
  try {
    // Создаем временный textarea
    const textArea = document.createElement('textarea');
    textArea.value = text;
    
    // Стили, чтобы элемент не был виден
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    textArea.style.opacity = '0';
    textArea.style.pointerEvents = 'none';
    textArea.style.zIndex = '-1000';
    
    document.body.appendChild(textArea);
    
    // Для мобильных iOS нужно особое выделение
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
    
    // Пытаемся скопировать
    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    
    return successful;
  } catch (err) {
    console.error('Fallback copy failed:', err);
    return false;
  }
}

// Функция для отображения уведомления на мобильных
function showMobileNotification(message) {
  // Создаем или находим контейнер для уведомлений
  let notificationContainer = document.getElementById('mobile-notification');
  if (!notificationContainer) {
    notificationContainer = document.createElement('div');
    notificationContainer.id = 'mobile-notification';
    notificationContainer.style.cssText = `
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
    document.body.appendChild(notificationContainer);
  }
  
  notificationContainer.textContent = message;
  notificationContainer.style.opacity = '1';
  
  setTimeout(() => {
    notificationContainer.style.opacity = '0';
    setTimeout(() => {
      if (notificationContainer.parentNode) {
        notificationContainer.textContent = '';
      }
    }, 300);
  }, 2000);
}

// Обработка элементов с классом copyable-text
document.querySelectorAll('.copyable-text').forEach(element => {
  const handleCopy = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    
    const textToCopy = element.getAttribute('data-clipboard-text') || element.textContent;
    const originalText = element.textContent;
    const originalColor = element.style.color;
    
    try {
      await copyToClipboard(textToCopy);
      
      // Для мобильных показываем уведомление
      if ('ontouchstart' in window) {
        showMobileNotification('Copied to clipboard!');
      }
      
      // Визуальная обратная связь для десктопа
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
  
  // Добавляем обработчики для всех типов событий
  element.addEventListener('click', handleCopy);
  element.addEventListener('touchstart', handleCopy, { passive: false });
  element.addEventListener('touchend', (e) => e.preventDefault());
});

// Обработка кнопки копирования кода
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
      
      // Для мобильных показываем уведомление
      if ('ontouchstart' in window) {
        showMobileNotification('Code copied to clipboard!');
      }
      
      // Визуальная обратная связь
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
  
  // Добавляем все возможные обработчики
  copyCodeButton.addEventListener('click', handleCopyCode);
  copyCodeButton.addEventListener('touchstart', handleCopyCode, { passive: false });
  copyCodeButton.addEventListener('touchend', (e) => e.preventDefault());
}

// Дополнительно: для iOS добавляем специальную обработку
if (navigator.userAgent.match(/ipad|iphone|ipod/i)) {
  // iOS часто требует явного user gesture для копирования
  document.addEventListener('touchstart', function() {}, { passive: true });
  
  // Также добавляем контекстное меню для копирования
  const codeInput = document.getElementById('codeInput');
  if (codeInput) {
    codeInput.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      // Показываем кастомное меню или сразу копируем
      handleCopyCode(e);
    });
  }
}