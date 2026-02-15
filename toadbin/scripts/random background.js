// Random Video Background Selector (MP4 version)
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
                console.warn('No background videos found on server');
                return;
            }
            
            // Выбираем случайный фон
            const randomIndex = Math.floor(Math.random() * backgrounds.length);
            const selectedBackground = backgrounds[randomIndex];
            
            // Находим видео-элемент
            const videoElement = document.querySelector('.gif-background');
            if (!videoElement) {
                console.warn('Video element with class .gif-background not found');
                return;
            }
            
            // Очищаем предыдущие источники и добавляем новый
            videoElement.innerHTML = ''; // удаляем все <source>
            const source = document.createElement('source');
            source.src = `/toadbin/static/backgrounds/${selectedBackground}`;
            source.type = 'video/mp4';
            videoElement.appendChild(source);
            
            // Убеждаемся, что нужные атрибуты установлены
            videoElement.autoplay = true;
            videoElement.loop = true;
            videoElement.muted = true; // обязательно для автоплея
            videoElement.playsInline = true; // для мобильных устройств
            
            // Перезагружаем видео
            videoElement.load();
            
            // Обработка ошибок загрузки
            videoElement.onerror = function() {
                console.warn(`Failed to load video: ${selectedBackground}`);
                // Пробуем другой случайный фон
                const fallbackIndex = (randomIndex + 1) % backgrounds.length;
                const fallbackSource = document.createElement('source');
                fallbackSource.src = `/toadbin/static/backgrounds/${backgrounds[fallbackIndex]}`;
                fallbackSource.type = 'video/mp4';
                videoElement.innerHTML = '';
                videoElement.appendChild(fallbackSource);
                videoElement.load();
            };
            
            console.log(`Selected background video: ${selectedBackground}`);
            
        } catch (error) {
            console.error('Error loading background list:', error);
            // Используем запасной вариант
            const videoElement = document.querySelector('.gif-background');
            if (videoElement) {
                videoElement.innerHTML = '';
                const source = document.createElement('source');
                // Путь к дефолтному видео (измените расширение на .mp4)
                source.src = '/toadbin/static/backgrounds/there is no god beyond.mp4';
                source.type = 'video/mp4';
                videoElement.appendChild(source);
                videoElement.load();
            }
        }
    }
    
    // Загружаем случайный фон
    loadRandomBackground();
});