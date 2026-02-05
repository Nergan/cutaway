// Функция для копирования текста с fallback
function copyToClipboard(text) {
  // Пробуем современный Clipboard API
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  } else {
    // Fallback для HTTP и старых браузеров
    return new Promise((resolve, reject) => {
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
        
        document.body.appendChild(textArea);
        
        // Выделяем и копируем
        textArea.select();
        textArea.setSelectionRange(0, textArea.value.length);
        
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
          resolve();
        } else {
          reject(new Error('Не удалось скопировать текст'));
        }
      } catch (err) {
        reject(err);
      }
    });
  }
}

// Обработка элементов с классом copyable-text
document.querySelectorAll('.copyable-text').forEach(element => {
  // Добавляем обработчик для click (десктоп) и touchstart (мобильные)
  const handleCopy = async (event) => {
    // Предотвращаем стандартное поведение для touch
    if (event.type === 'touchstart') {
      event.preventDefault();
    }
    
    const textToCopy = element.getAttribute('data-clipboard-text') || element.textContent;
    const originalText = element.textContent;
    const originalColor = element.style.color;
    
    try {
      await copyToClipboard(textToCopy);
      
      // Визуальная обратная связь
      element.textContent = 'Copied!';
      element.style.color = '#28a745';
      
      // Возвращаем исходный текст через 2 секунды
      setTimeout(() => {
        element.textContent = originalText;
        element.style.color = originalColor;
      }, 2000);
      
    } catch (err) {
      console.error('Ошибка при копировании: ', err);
      element.textContent = 'Error :(';
      element.style.color = '#dc3545';
      
      setTimeout(() => {
        element.textContent = originalText;
        element.style.color = originalColor;
      }, 2000);
    }
  };
  
  // Добавляем оба обработчика
  element.addEventListener('click', handleCopy);
  element.addEventListener('touchstart', handleCopy, { passive: false });
});

// Обработка кнопки копирования кода
const copyCodeButton = document.getElementById('copyCodeButton');
if (copyCodeButton) {
  const handleCopyCode = async (event) => {
    // Предотвращаем стандартное поведение для touch
    if (event.type === 'touchstart') {
      event.preventDefault();
    }
    
    const codeInput = document.getElementById('codeInput');
    if (!codeInput) return;
    
    const codeToCopy = codeInput.value;
    const originalHTML = copyCodeButton.innerHTML;
    const originalTitle = copyCodeButton.getAttribute('title');
    const originalClass = copyCodeButton.className;
    
    try {
      await copyToClipboard(codeToCopy);
      
      // Визуальная обратная связь
      copyCodeButton.innerHTML = '<i class="bi bi-check2"></i>';
      copyCodeButton.setAttribute('title', 'Code copied!');
      copyCodeButton.className = originalClass + ' copied';
      
      // Возвращаем исходное состояние через 2 секунды
      setTimeout(() => {
        copyCodeButton.innerHTML = originalHTML;
        copyCodeButton.setAttribute('title', originalTitle);
        copyCodeButton.className = originalClass;
      }, 2000);
      
    } catch (err) {
      console.error('Ошибка при копировании кода: ', err);
      copyCodeButton.innerHTML = '<i class="bi bi-x"></i>';
      copyCodeButton.setAttribute('title', 'Copy failed');
      
      setTimeout(() => {
        copyCodeButton.innerHTML = originalHTML;
        copyCodeButton.setAttribute('title', originalTitle);
      }, 2000);
    }
  };
  
  // Добавляем оба обработчика
  copyCodeButton.addEventListener('click', handleCopyCode);
  copyCodeButton.addEventListener('touchstart', handleCopyCode, { passive: false });
}

// Также добавим стиль для улучшения touch-обработки на мобильных
const style = document.createElement('style');
style.textContent = `
  .copyable-text, #copyCodeButton {
    -webkit-tap-highlight-color: rgba(0, 255, 0, 0.3);
    tap-highlight-color: rgba(0, 255, 0, 0.3);
    user-select: none;
  }
  
  @media (max-width: 768px) {
    .copyable-text, #copyCodeButton {
      min-height: 44px; /* Минимальный размер для touch-целей */
      min-width: 44px;
    }
  }
`;
document.head.appendChild(style);