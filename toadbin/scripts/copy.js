document.querySelectorAll('.copyable-text').forEach(element => {
  element.addEventListener('click', async (event) => {
    // Копируем содержимое элемента, на который кликнули
    const textToCopy = event.currentTarget.textContent;
    
    // Сохраняем исходный текст для восстановления
    const originalText = element.textContent;
    
    try {
      // Используем современный Clipboard API
      await navigator.clipboard.writeText(textToCopy);
      
      // Визуальная обратная связь
      element.textContent = 'Copied!';
      element.style.color = '#28a745';
      
      // Возвращаем исходный текст через 2 секунды
      setTimeout(() => {
        element.textContent = originalText;
        element.style.color = '';
      }, 2000);
      
    } catch (err) {
      console.error('Ошибка при копировании: ', err);
      element.textContent = 'Error :(';
      element.style.color = '#dc3545';
      
      setTimeout(() => {
        element.textContent = originalText;
        element.style.color = '';
      }, 2000);
    }
  });
});

// Обработка кнопки копирования кода
const copyCodeButton = document.getElementById('copyCodeButton');
if (copyCodeButton) {
  copyCodeButton.addEventListener('click', async () => {
    const codeInput = document.getElementById('codeInput');
    if (!codeInput) return;
    
    const codeToCopy = codeInput.value;
    const originalHTML = copyCodeButton.innerHTML;
    const originalTitle = copyCodeButton.getAttribute('title');
    
    try {
      // Используем современный Clipboard API
      await navigator.clipboard.writeText(codeToCopy);
      
      // Визуальная обратная связь
      copyCodeButton.innerHTML = '<i class="bi bi-check2"></i>';
      copyCodeButton.setAttribute('title', 'Code copied!');
      copyCodeButton.classList.add('copied');
      
      // Возвращаем исходное состояние через 2 секунды
      setTimeout(() => {
        copyCodeButton.innerHTML = originalHTML;
        copyCodeButton.setAttribute('title', originalTitle);
        copyCodeButton.classList.remove('copied');
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
  });
}