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