document.addEventListener('DOMContentLoaded', function() {
    // Получаем элементы DOM
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');
    const particlesCanvas = document.getElementById('particlesCanvas');
    const particlesCtx = particlesCanvas.getContext('2d');
    
    // Элементы UI
    const scoreElement = document.getElementById('score');
    const levelElement = document.getElementById('level');
    const lengthElement = document.getElementById('length');
    const finalScoreElement = document.getElementById('finalScore');
    const finalLevelElement = document.getElementById('finalLevel');
    const finalLengthElement = document.getElementById('finalLength');
    
    // Кнопки
    const startBtn = document.getElementById('startBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const restartBtn = document.getElementById('restartBtn');
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const startGameBtn = document.getElementById('startGameBtn');
    const resumeBtn = document.getElementById('resumeBtn');
    const playAgainBtn = document.getElementById('playAgainBtn');
    
    // Экранные оверлеи
    const startScreen = document.getElementById('startScreen');
    const pauseScreen = document.getElementById('pauseScreen');
    const gameOverScreen = document.getElementById('gameOverScreen');
    
    // Индикатор направления
    const directionIndicator = document.getElementById('directionIndicator');
    const arrows = directionIndicator.querySelectorAll('.arrow');
    
    // Размеры холста
    let canvasWidth, canvasHeight;
    
    // Константы игры
    const GRID_SIZE = 25;
    let GRID_WIDTH, GRID_HEIGHT;
    
    // Переменные игры
    let snake = [];
    let food = {};
    let direction = 'right';
    let nextDirection = 'right';
    let gameRunning = false;
    let gamePaused = false;
    let score = 0;
    let level = 1;
    let snakeLength = 3;
    let gameSpeed = 120;
    let gameLoop;
    let particles = [];
    
    // Инициализация размеров
    function initCanvasSize() {
        const container = canvas.parentElement;
        const maxWidth = container.clientWidth * 0.96;
        const maxHeight = container.clientHeight * 0.90;
        
        // Сохраняем соотношение сторон 16:9
        const aspectRatio = 16/9;
        
        if (maxWidth / aspectRatio <= maxHeight) {
            canvasWidth = maxWidth;
            canvasHeight = maxWidth / aspectRatio;
        } else {
            canvasHeight = maxHeight;
            canvasWidth = maxHeight * aspectRatio;
        }
        
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        
        // Обновляем размеры сетки
        GRID_WIDTH = Math.floor(canvasWidth / GRID_SIZE);
        GRID_HEIGHT = Math.floor(canvasHeight / GRID_SIZE);
        
        // Устанавливаем размеры для particlesCanvas
        particlesCanvas.width = window.innerWidth;
        particlesCanvas.height = window.innerHeight;
    }
    
    // Инициализация игры
    function initGame() {
        // Инициализация змейки
        const startX = Math.floor(GRID_WIDTH / 4);
        const startY = Math.floor(GRID_HEIGHT / 2);
        
        snake = [];
        for (let i = 0; i < 3; i++) {
            snake.push({x: startX - i, y: startY});
        }
        
        // Генерация первой еды
        generateFood();
        
        // Сброс направления
        direction = 'right';
        nextDirection = 'right';
        updateDirectionIndicator();
        
        // Сброс счета и уровня
        score = 0;
        level = 1;
        snakeLength = 3;
        gameSpeed = 120;
        
        // Обновление UI
        scoreElement.textContent = score;
        levelElement.textContent = level;
        lengthElement.textContent = snakeLength;
        
        // Скрытие экранов
        startScreen.style.display = 'none';
        pauseScreen.style.display = 'none';
        gameOverScreen.style.display = 'none';
        
        // Начало игры
        gameRunning = true;
        gamePaused = false;
        
        // Очистка частиц
        particles = [];
        
        // Запуск игрового цикла
        if (gameLoop) clearInterval(gameLoop);
        gameLoop = setInterval(update, gameSpeed);
        
        // Первая отрисовка
        draw();
        drawParticles();
    }
    
    // Генерация еды
    function generateFood() {
        // Генерация случайной позиции для еды
        const foodTypes = ['normal', 'special', 'bonus'];
        const weights = [0.7, 0.2, 0.1]; // 70% обычная, 20% особенная, 10% бонусная
        
        let random = Math.random();
        let typeIndex = 0;
        let cumulativeWeight = 0;
        
        for (let i = 0; i < weights.length; i++) {
            cumulativeWeight += weights[i];
            if (random < cumulativeWeight) {
                typeIndex = i;
                break;
            }
        }
        
        food = {
            x: Math.floor(Math.random() * GRID_WIDTH),
            y: Math.floor(Math.random() * GRID_HEIGHT),
            type: foodTypes[typeIndex]
        };
        
        // Проверка, чтобы еда не появилась на змейке
        for (let segment of snake) {
            if (segment.x === food.x && segment.y === food.y) {
                return generateFood();
            }
        }
        
        // Создаем эффект появления еды
        let particleColor;
        switch(food.type) {
            case 'normal': particleColor = 'green'; break;
            case 'special': particleColor = 'blue'; break;
            case 'bonus': particleColor = 'yellow'; break;
        }
        
        createParticles(food.x * GRID_SIZE + GRID_SIZE/2, food.y * GRID_SIZE + GRID_SIZE/2, 
                       particleColor, 20);
    }
    
    // Создание частиц
    function createParticles(x, y, color, count) {
        for (let i = 0; i < count; i++) {
            particles.push({
                x: x,
                y: y,
                size: Math.random() * 4 + 2,
                speedX: (Math.random() - 0.5) * 6,
                speedY: (Math.random() - 0.5) * 6,
                color: color,
                life: 1.0,
                decay: Math.random() * 0.05 + 0.02
            });
        }
    }
    
    // Отрисовка частиц
    function drawParticles() {
        particlesCtx.clearRect(0, 0, particlesCanvas.width, particlesCanvas.height);
        
        for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];
            
            particlesCtx.beginPath();
            particlesCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            
            // Назначаем цвет в зависимости от типа
            if (p.color === 'green') {
                particlesCtx.fillStyle = `rgba(0, 255, 136, ${p.life})`;
                particlesCtx.shadowColor = '#00ff88';
            } else if (p.color === 'blue') {
                particlesCtx.fillStyle = `rgba(0, 204, 255, ${p.life})`;
                particlesCtx.shadowColor = '#00ccff';
            } else if (p.color === 'pink') {
                particlesCtx.fillStyle = `rgba(255, 0, 204, ${p.life})`;
                particlesCtx.shadowColor = '#ff00cc';
            } else if (p.color === 'yellow') {
                particlesCtx.fillStyle = `rgba(255, 255, 0, ${p.life})`;
                particlesCtx.shadowColor = '#ffff00';
            } else if (p.color === 'purple') {
                particlesCtx.fillStyle = `rgba(170, 0, 255, ${p.life})`;
                particlesCtx.shadowColor = '#aa00ff';
            }
            
            particlesCtx.shadowBlur = 15;
            particlesCtx.fill();
            particlesCtx.shadowBlur = 0;
            
            // Обновление частиц
            p.x += p.speedX;
            p.y += p.speedY;
            p.life -= p.decay;
            
            // Удаление частиц с истекшим сроком жизни
            if (p.life <= 0) {
                particles.splice(i, 1);
            }
        }
    }
    
    // Отрисовка игры
    function draw() {
        // Очистка холста
        ctx.fillStyle = 'rgba(0, 0, 0, 0.98)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Отрисовка сетки (очень тонкая)
        drawGrid();
        
        // Отрисовка змейки
        drawSnake();
        
        // Отрисовка еды
        drawFood();
    }
    
    // Отрисовка сетки
    function drawGrid() {
        ctx.strokeStyle = 'rgba(0, 255, 136, 0.05)';
        ctx.lineWidth = 0.5;
        
        // Вертикальные линии
        for (let x = 0; x <= canvas.width; x += GRID_SIZE) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.stroke();
        }
        
        // Горизонтальные линии
        for (let y = 0; y <= canvas.height; y += GRID_SIZE) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }
    }
    
    // Отрисовка змейки
    function drawSnake() {
        // Отрисовка тела змейки
        for (let i = 0; i < snake.length; i++) {
            const segment = snake[i];
            const x = segment.x * GRID_SIZE;
            const y = segment.y * GRID_SIZE;
            
            // Градиент для змейки (голова ярче)
            let gradient;
            if (i === 0) {
                // Голова змейки
                gradient = ctx.createRadialGradient(
                    x + GRID_SIZE/2, y + GRID_SIZE/2, 0,
                    x + GRID_SIZE/2, y + GRID_SIZE/2, GRID_SIZE/2
                );
                
                // Разные неоновые цвета для разных направлений
                if (direction === 'right') {
                    gradient.addColorStop(0, '#00ff88'); // Неоновый зеленый
                    gradient.addColorStop(0.7, '#00cc66');
                    gradient.addColorStop(1, 'rgba(0, 204, 102, 0.2)');
                } else if (direction === 'left') {
                    gradient.addColorStop(0, '#00ccff'); // Неоновый голубой
                    gradient.addColorStop(0.7, '#00aadd');
                    gradient.addColorStop(1, 'rgba(0, 170, 221, 0.2)');
                } else if (direction === 'up') {
                    gradient.addColorStop(0, '#ff00cc'); // Неоновый розовый
                    gradient.addColorStop(0.7, '#cc00aa');
                    gradient.addColorStop(1, 'rgba(204, 0, 170, 0.2)');
                } else {
                    gradient.addColorStop(0, '#ffff00'); // Неоновый желтый
                    gradient.addColorStop(0.7, '#cccc00');
                    gradient.addColorStop(1, 'rgba(204, 204, 0, 0.2)');
                }
                
                // Глаза змейки
                ctx.fillStyle = '#000';
                const eyeSize = GRID_SIZE / 5;
                const eyeOffsetX = direction === 'right' ? GRID_SIZE * 0.7 : 
                                 direction === 'left' ? GRID_SIZE * 0.3 : GRID_SIZE * 0.5;
                const eyeOffsetY = direction === 'up' ? GRID_SIZE * 0.3 : 
                                 direction === 'down' ? GRID_SIZE * 0.7 : GRID_SIZE * 0.5;
                
                // Левый глаз
                ctx.beginPath();
                ctx.arc(
                    x + eyeOffsetX - (direction === 'left' ? 0 : direction === 'right' ? 0 : GRID_SIZE * 0.15), 
                    y + eyeOffsetY - (direction === 'up' ? 0 : direction === 'down' ? 0 : GRID_SIZE * 0.15), 
                    eyeSize, 0, Math.PI * 2
                );
                ctx.fill();
                
                // Правый глаз
                ctx.beginPath();
                ctx.arc(
                    x + eyeOffsetX + (direction === 'left' ? 0 : direction === 'right' ? 0 : GRID_SIZE * 0.15), 
                    y + eyeOffsetY + (direction === 'up' ? 0 : direction === 'down' ? 0 : GRID_SIZE * 0.15), 
                    eyeSize, 0, Math.PI * 2
                );
                ctx.fill();
                
                // Язык (только при движении)
                if (direction === 'right') {
                    ctx.fillStyle = '#ff0000';
                    ctx.beginPath();
                    ctx.moveTo(x + GRID_SIZE, y + GRID_SIZE/2);
                    ctx.lineTo(x + GRID_SIZE + 5, y + GRID_SIZE/2 - 3);
                    ctx.lineTo(x + GRID_SIZE + 5, y + GRID_SIZE/2 + 3);
                    ctx.closePath();
                    ctx.fill();
                }
            } else {
                // Тело змейки - чередующиеся неоновые цвета
                gradient = ctx.createRadialGradient(
                    x + GRID_SIZE/2, y + GRID_SIZE/2, 0,
                    x + GRID_SIZE/2, y + GRID_SIZE/2, GRID_SIZE/2
                );
                
                // Цвет меняется в зависимости от позиции в теле
                const intensity = 0.4 + (1 - i / snake.length) * 0.6;
                
                // Чередование неоновых цветов
                if (i % 4 === 0) {
                    gradient.addColorStop(0, `rgba(0, 255, 136, ${intensity})`);
                    gradient.addColorStop(1, `rgba(0, 255, 136, ${intensity * 0.3})`);
                } else if (i % 4 === 1) {
                    gradient.addColorStop(0, `rgba(0, 204, 255, ${intensity})`);
                    gradient.addColorStop(1, `rgba(0, 204, 255, ${intensity * 0.3})`);
                } else if (i % 4 === 2) {
                    gradient.addColorStop(0, `rgba(255, 0, 204, ${intensity})`);
                    gradient.addColorStop(1, `rgba(255, 0, 204, ${intensity * 0.3})`);
                } else {
                    gradient.addColorStop(0, `rgba(255, 255, 0, ${intensity})`);
                    gradient.addColorStop(1, `rgba(255, 255, 0, ${intensity * 0.3})`);
                }
            }
            
            // Отрисовка сегмента
            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.roundRect(x, y, GRID_SIZE, GRID_SIZE, 7);
            ctx.fill();
            
            // Обводка сегмента
            ctx.strokeStyle = i === 0 ? '#fff' : 'rgba(255, 255, 255, 0.4)';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            // Эффект свечения
            ctx.shadowColor = i === 0 ? '#00ff88' : 
                             i % 4 === 0 ? '#00ff88' :
                             i % 4 === 1 ? '#00ccff' :
                             i % 4 === 2 ? '#ff00cc' : '#ffff00';
            ctx.shadowBlur = 10;
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
    }
    
    // Отрисовка еды
    function drawFood() {
        const x = food.x * GRID_SIZE + GRID_SIZE/2;
        const y = food.y * GRID_SIZE + GRID_SIZE/2;
        
        // Создаем градиент для неонового свечения
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, GRID_SIZE/2);
        
        if (food.type === 'special') {
            // Особенная еда - голубая
            gradient.addColorStop(0, '#00ccff');
            gradient.addColorStop(0.5, '#00aadd');
            gradient.addColorStop(1, 'rgba(0, 170, 221, 0.1)');
            
            // Пульсация
            const pulse = Math.sin(Date.now() / 200) * 0.3 + 0.7;
            ctx.shadowColor = '#00ccff';
            ctx.shadowBlur = 25 * pulse;
        } else if (food.type === 'bonus') {
            // Бонусная еда - желтая
            gradient.addColorStop(0, '#ffff00');
            gradient.addColorStop(0.5, '#cccc00');
            gradient.addColorStop(1, 'rgba(204, 204, 0, 0.1)');
            
            // Пульсация
            const pulse = Math.sin(Date.now() / 150) * 0.4 + 0.6;
            ctx.shadowColor = '#ffff00';
            ctx.shadowBlur = 30 * pulse;
        } else {
            // Обычная еда - зеленая
            gradient.addColorStop(0, '#00ff88');
            gradient.addColorStop(0.5, '#00cc66');
            gradient.addColorStop(1, 'rgba(0, 204, 102, 0.1)');
            
            ctx.shadowColor = '#00ff88';
            ctx.shadowBlur = 20;
        }
        
        // Отрисовка еды
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, GRID_SIZE/2 - 3, 0, Math.PI * 2);
        ctx.fill();
        
        // Рисуем неоновый узор на еде
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x - GRID_SIZE/4, y);
        ctx.lineTo(x + GRID_SIZE/4, y);
        ctx.moveTo(x, y - GRID_SIZE/4);
        ctx.lineTo(x, y + GRID_SIZE/4);
        ctx.stroke();
        
        // Сброс тени
        ctx.shadowBlur = 0;
    }
    
    // Обновление игрового состояния
    function update() {
        if (!gameRunning || gamePaused) return;
        
        // Обновление направления
        direction = nextDirection;
        updateDirectionIndicator();
        
        // Создание новой головы змейки
        const head = {...snake[0]};
        
        // Перемещение головы в зависимости от направления
        switch(direction) {
            case 'up': head.y -= 1; break;
            case 'down': head.y += 1; break;
            case 'left': head.x -= 1; break;
            case 'right': head.x += 1; break;
        }
        
        // Телепортация через границы
        if (head.x < 0) head.x = GRID_WIDTH - 1;
        if (head.x >= GRID_WIDTH) head.x = 0;
        if (head.y < 0) head.y = GRID_HEIGHT - 1;
        if (head.y >= GRID_HEIGHT) head.y = 0;
        
        // Проверка столкновения с собой
        for (let i = 0; i < snake.length; i++) {
            const segment = snake[i];
            if (head.x === segment.x && head.y === segment.y) {
                gameOver();
                return;
            }
        }
        
        // Добавление новой головы
        snake.unshift(head);
        
        // Проверка съедения еды
        if (head.x === food.x && head.y === food.y) {
            // Создаем частицы при съедении
            let particleColor;
            switch(food.type) {
                case 'normal': particleColor = 'green'; break;
                case 'special': particleColor = 'blue'; break;
                case 'bonus': particleColor = 'yellow'; break;
            }
            
            createParticles(
                head.x * GRID_SIZE + GRID_SIZE/2,
                head.y * GRID_SIZE + GRID_SIZE/2,
                particleColor,
                25
            );
            
            // Увеличение счета в зависимости от типа еды
            if (food.type === 'special') {
                score += 3;
            } else if (food.type === 'bonus') {
                score += 5;
            } else {
                score += 1;
            }
            
            snakeLength = snake.length;
            
            // Обновление UI
            scoreElement.textContent = score;
            lengthElement.textContent = snakeLength;
            
            // Обновление уровня каждые 5 очков
            const newLevel = Math.floor(score / 5) + 1;
            if (newLevel > level) {
                level = newLevel;
                levelElement.textContent = level;
                
                // Увеличение скорости игры
                gameSpeed = Math.max(50, 120 - (level - 1) * 10);
                
                // Перезапуск игрового цикла с новой скоростью
                clearInterval(gameLoop);
                gameLoop = setInterval(update, gameSpeed);
                
                // Эффект при повышении уровня
                createParticles(canvas.width/2, canvas.height/2, 'purple', 40);
            }
            
            // Генерация новой еды
            generateFood();
        } else {
            // Удаление хвоста, если еда не съедена
            snake.pop();
        }
        
        // Отрисовка обновленного состояния
        draw();
        drawParticles();
    }
    
    // Обновление индикатора направления
    function updateDirectionIndicator() {
        arrows.forEach(arrow => arrow.classList.remove('active'));
        
        switch(direction) {
            case 'up':
                document.querySelector('.arrow.up').classList.add('active');
                break;
            case 'down':
                document.querySelector('.arrow.down').classList.add('active');
                break;
            case 'left':
                document.querySelector('.arrow.left').classList.add('active');
                break;
            case 'right':
                document.querySelector('.arrow.right').classList.add('active');
                break;
        }
    }
    
    // Конец игры
    function gameOver() {
        gameRunning = false;
        clearInterval(gameLoop);
        
        // Создаем частицы при окончании игры
        for (let segment of snake) {
            createParticles(
                segment.x * GRID_SIZE + GRID_SIZE/2,
                segment.y * GRID_SIZE + GRID_SIZE/2,
                'pink',
                8
            );
        }
        
        // Показ экрана окончания игры
        finalScoreElement.textContent = score;
        finalLevelElement.textContent = level;
        finalLengthElement.textContent = snakeLength;
        gameOverScreen.style.display = 'flex';
    }
    
    // Пауза игры
    function togglePause() {
        if (!gameRunning) return;
        
        gamePaused = !gamePaused;
        
        if (gamePaused) {
            pauseScreen.style.display = 'flex';
        } else {
            pauseScreen.style.display = 'none';
        }
    }
    
    // Переключение полноэкранного режима
    function toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.log(`Ошибка при попытке перейти в полноэкранный режим: ${err.message}`);
            });
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
    }
    
    // Обработка нажатия клавиш - независимо от раскладки
    function handleKeyDown(e) {
        // Изменение направления движения - используем event.code, а не event.key
        // Это работает независимо от раскладки клавиатуры
        if (gameRunning) {
            switch(e.code) {
                case 'KeyW':
                case 'ArrowUp':
                    if (direction !== 'down') nextDirection = 'up';
                    e.preventDefault();
                    break;
                case 'KeyS':
                case 'ArrowDown':
                    if (direction !== 'up') nextDirection = 'down';
                    e.preventDefault();
                    break;
                case 'KeyA':
                case 'ArrowLeft':
                    if (direction !== 'right') nextDirection = 'left';
                    e.preventDefault();
                    break;
                case 'KeyD':
                case 'ArrowRight':
                    if (direction !== 'left') nextDirection = 'right';
                    e.preventDefault();
                    break;
            }
        }
        
        // Остальные клавиши управления
        switch(e.code) {
            case 'Space':
                // Старт/пауза при нажатии пробела
                if (!gameRunning && startScreen.style.display !== 'none') {
                    initGame();
                } else if (gameRunning) {
                    togglePause();
                }
                e.preventDefault();
                break;
            case 'KeyP':
                // Пауза
                if (gameRunning) {
                    togglePause();
                }
                e.preventDefault();
                break;
            case 'KeyR':
                // Рестарт
                initGame();
                e.preventDefault();
                break;
            case 'KeyF':
                // Полноэкранный режим
                toggleFullscreen();
                e.preventDefault();
                break;
            case 'Escape':
                // Выход из полноэкранного режима
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                }
                break;
        }
    }
    
    // Инициализация управления
    function initControls() {
        // Обработка нажатий клавиш
        document.addEventListener('keydown', handleKeyDown);
        
        // Обработка кликов по кнопкам
        startBtn.addEventListener('click', () => {
            if (!gameRunning) {
                initGame();
            } else {
                togglePause();
            }
        });
        
        pauseBtn.addEventListener('click', togglePause);
        
        restartBtn.addEventListener('click', initGame);
        
        fullscreenBtn.addEventListener('click', toggleFullscreen);
        
        startGameBtn.addEventListener('click', initGame);
        
        resumeBtn.addEventListener('click', () => {
            gamePaused = false;
            pauseScreen.style.display = 'none';
        });
        
        playAgainBtn.addEventListener('click', initGame);
        
        // Обработка изменения размера окна
        window.addEventListener('resize', () => {
            initCanvasSize();
            draw();
            drawParticles();
        });
        
        // Обработка полноэкранного режима
        document.addEventListener('fullscreenchange', () => {
            setTimeout(() => {
                initCanvasSize();
                draw();
                drawParticles();
            }, 100);
        });
    }
    
    // Анимация частиц
    function animateParticles() {
        drawParticles();
        requestAnimationFrame(animateParticles);
    }
    
    // Инициализация при загрузке страницы
    function init() {
        initCanvasSize();
        initControls();
        animateParticles();
        
        // Отображаем стартовый экран
        startScreen.style.display = 'flex';
    }
    
    // Запуск инициализации
    init();
});