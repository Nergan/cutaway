// Random Background Selector
document.addEventListener('DOMContentLoaded', function() {
    async function loadRandomBackground() {
        try {
            // Запрашиваем список доступных фонов у сервера
            const response = await fetch('/api/backgrounds');
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            const backgrounds = data.backgrounds;
            
            if (!backgrounds || backgrounds.length === 0) {
                console.warn('No background images found on server');
                return;
            }
            
            // Выбираем случайный фон
            const randomIndex = Math.floor(Math.random() * backgrounds.length);
            const selectedBackground = backgrounds[randomIndex];
            
            // Устанавливаем выбранный фон - используем абсолютный путь!
            const bgElement = document.querySelector('.gif-background');
            if (bgElement) {
                bgElement.src = `/toadbin/static/backgrounds/${selectedBackground}`;
                
                // Обработка ошибок загрузки
                bgElement.onerror = function() {
                    console.warn(`Failed to load background: ${selectedBackground}`);
                    // Пробуем другой случайный фон
                    const fallbackIndex = (randomIndex + 1) % backgrounds.length;
                    bgElement.src = `/toadbin/static/backgrounds/${backgrounds[fallbackIndex]}`;
                };
                
                console.log(`Selected background: ${selectedBackground}`);
            }
            
        } catch (error) {
            console.error('Error loading background list:', error);
            // Можно использовать запасной вариант или дефолтный фон
            const bgElement = document.querySelector('.gif-background');
            if (bgElement) {
                // Используем абсолютный путь
                bgElement.src = '/toadbin/static/backgrounds/there is no god beyond.gif';
            }
        }
    }
    
    // Загружаем случайный фон
    loadRandomBackground();
});