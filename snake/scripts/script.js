document.addEventListener('DOMContentLoaded', function() {
    // ========== ВИДЕО-ФОН (динамический выбор из папки backgrounds) ==========
    const videoBg = document.getElementById('bgVideo');

    async function setRandomVideo() {
        let videoList = null;

        // 1. Пытаемся получить список через API-эндпоинт (правильный путь с префиксом /snake)
        try {
            const response = await fetch('/api/snake-backgrounds');
            if (response.ok) {
                const text = await response.text();
                // Проверяем, что это JSON, а не HTML
                try {
                    const data = JSON.parse(text);
                    if (data.backgrounds && Array.isArray(data.backgrounds)) {
                        videoList = data.backgrounds;
                    }
                    if (videoList && videoList.length > 0) {
                        console.log('Список видео получен через API');
                    }
                } catch (e) {
                    console.warn('API вернул не JSON, возможно ошибка 404');
                }
            }
        } catch (err) {
            console.warn('API недоступен:', err);
        }

        const randomIndex = Math.floor(Math.random() * videoList.length);
        const selectedVideo = videoList[randomIndex];
        const videoPath = `/snake/static/backgrounds/${selectedVideo}`;

        // Очищаем предыдущие источники
        videoBg.innerHTML = '';
        const source = document.createElement('source');
        source.src = videoPath;
        source.type = 'video/mp4';
        videoBg.appendChild(source);

        // Устанавливаем атрибуты для автовоспроизведения
        videoBg.autoplay = true;
        videoBg.loop = true;
        videoBg.muted = true;
        videoBg.playsInline = true;

        videoBg.load();

        // Если видео не загрузилось – пробуем другое
        videoBg.onerror = () => {
            console.warn(`Не удалось загрузить видео: ${selectedVideo}`);
            const fallbackIndex = (randomIndex + 1) % videoList.length;
            const fallbackPath = `/snake/static/backgrounds/${videoList[fallbackIndex]}`;
            videoBg.innerHTML = '';
            const newSource = document.createElement('source');
            newSource.src = fallbackPath;
            newSource.type = 'video/mp4';
            videoBg.appendChild(newSource);
            videoBg.load();
        };

        console.log(`Выбрано видео фона: ${selectedVideo}`);
    }

    if (videoBg) {
        setRandomVideo();
    }

    // ========== ДАЛЕЕ ВЕСЬ КОД ИГРЫ (БЕЗ ИЗМЕНЕНИЙ) ==========
    // Получаем элементы DOM
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');
    const particlesCanvas = document.getElementById('particlesCanvas');
    const particlesCtx = particlesCanvas.getContext('2d');

    const scoreElement = document.getElementById('score');
    const levelElement = document.getElementById('level');
    const lengthElement = document.getElementById('length');
    const finalScoreElement = document.getElementById('finalScore');
    const finalLevelElement = document.getElementById('finalLevel');
    const finalLengthElement = document.getElementById('finalLength');

    const startBtn = document.getElementById('startBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const restartBtn = document.getElementById('restartBtn');
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const startGameBtn = document.getElementById('startGameBtn');
    const resumeBtn = document.getElementById('resumeBtn');
    const playAgainBtn = document.getElementById('playAgainBtn');

    const startScreen = document.getElementById('startScreen');
    const pauseScreen = document.getElementById('pauseScreen');
    const gameOverScreen = document.getElementById('gameOverScreen');

    const directionIndicator = document.getElementById('directionIndicator');
    const arrows = directionIndicator.querySelectorAll('.arrow');

    // Вспомогательная функция для скруглённых прямоугольников
    function roundRect(ctx, x, y, w, h, r) {
        if (w < 2 * r) r = w / 2;
        if (h < 2 * r) r = h / 2;
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
        return ctx;
    }

    let canvasWidth, canvasHeight;
    const GRID_SIZE = 25;
    let GRID_WIDTH, GRID_HEIGHT;

    let snake = [];
    let food = {};
    let direction = 'right';
    let nextDirection = 'right';
    let gameRunning = false;
    let gamePaused = false;
    let score = 0;
    let level = 1;
    let snakeLength = 3;
    let gameSpeed = 140;
    let gameLoop;
    let particles = [];

    // Инициализация размеров холста
    function initCanvasSize() {
        const container = canvas.parentElement;
        // Ограничим максимальные размеры с учётом отступов интерфейса
        const maxWidth = Math.min(window.innerWidth * 0.92, 1200);
        const maxHeight = window.innerHeight * 0.82;
        const aspectRatio = 16 / 9;

        let newWidth = maxWidth;
        let newHeight = newWidth / aspectRatio;
        if (newHeight > maxHeight) {
            newHeight = maxHeight;
            newWidth = newHeight * aspectRatio;
        }

        canvas.width = newWidth;
        canvas.height = newHeight;
        // Обновляем CSS-размеры, чтобы canvas был чётко видим
        canvas.style.width = `${newWidth}px`;
        canvas.style.height = `${newHeight}px`;

        GRID_WIDTH = Math.floor(canvas.width / GRID_SIZE);
        GRID_HEIGHT = Math.floor(canvas.height / GRID_SIZE);
        particlesCanvas.width = window.innerWidth;
        particlesCanvas.height = window.innerHeight;
    }

    // Инициализация игры
    function initGame() {
        const startX = Math.floor(GRID_WIDTH / 4);
        const startY = Math.floor(GRID_HEIGHT / 2);
        snake = [];
        for (let i = 0; i < 3; i++) {
            snake.push({ x: startX - i, y: startY });
        }
        generateFood();
        direction = 'right';
        nextDirection = 'right';
        updateDirectionIndicator();
        score = 0;
        level = 1;
        snakeLength = 3;
        gameSpeed = 140;
        scoreElement.textContent = score;
        levelElement.textContent = level;
        lengthElement.textContent = snakeLength;
        startScreen.style.display = 'none';
        pauseScreen.style.display = 'none';
        gameOverScreen.style.display = 'none';
        gameRunning = true;
        gamePaused = false;
        particles = [];
        if (gameLoop) clearInterval(gameLoop);
        gameLoop = setInterval(update, gameSpeed);
        draw();
        drawParticles();
    }

    // Генерация еды
    function generateFood() {
        const foodTypes = ['normal', 'special', 'bonus'];
        const weights = [0.7, 0.2, 0.1];
        let random = Math.random();
        let typeIndex = 0;
        let cumulative = 0;
        for (let i = 0; i < weights.length; i++) {
            cumulative += weights[i];
            if (random < cumulative) {
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
        for (let seg of snake) {
            if (seg.x === food.x && seg.y === food.y) return generateFood();
        }
        let color = food.type === 'normal' ? 'softgreen' : (food.type === 'special' ? 'softamber' : 'softcream');
        createParticles(food.x * GRID_SIZE + GRID_SIZE / 2, food.y * GRID_SIZE + GRID_SIZE / 2, color, 12);
    }

    // Создание частиц
    function createParticles(x, y, color, count) {
        for (let i = 0; i < count; i++) {
            particles.push({
                x: x, y: y,
                size: Math.random() * 5 + 2,
                speedX: (Math.random() - 0.5) * 5,
                speedY: (Math.random() - 0.5) * 5,
                color: color,
                life: 0.8 + Math.random() * 0.3,
                decay: Math.random() * 0.03 + 0.015
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
            let r, g, b;
            if (p.color === 'softgreen') {
                r = 100; g = 150; b = 80;
            } else if (p.color === 'softamber') {
                r = 180; g = 140; b = 70;
            } else if (p.color === 'softcream') {
                r = 220; g = 200; b = 130;
            } else if (p.color === 'softbrown') {
                r = 140; g = 100; b = 70;
            } else {
                r = 180; g = 160; b = 110;
            }
            particlesCtx.fillStyle = `rgba(${r}, ${g}, ${b}, ${p.life * 0.7})`;
            particlesCtx.shadowBlur = 6;
            particlesCtx.shadowColor = "rgba(180,150,80,0.5)";
            particlesCtx.fill();
            p.x += p.speedX;
            p.y += p.speedY;
            p.life -= p.decay;
            if (p.life <= 0) particles.splice(i, 1);
        }
        particlesCtx.shadowBlur = 0;
    }

    // Отрисовка сетки
    function drawGrid() {
        ctx.strokeStyle = 'rgba(180, 160, 110, 0.2)';
        ctx.lineWidth = 0.6;
        for (let x = 0; x <= canvas.width; x += GRID_SIZE) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.stroke();
        }
        for (let y = 0; y <= canvas.height; y += GRID_SIZE) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }
    }

    // Отрисовка змейки
    function drawSnake() {
        for (let i = 0; i < snake.length; i++) {
            const seg = snake[i];
            const x = seg.x * GRID_SIZE;
            const y = seg.y * GRID_SIZE;
            const size = GRID_SIZE;
            const isHead = (i === 0);
            let fillColor;
            if (isHead) {
                fillColor = `rgba(150, 190, 110, 0.75)`;
            } else {
                const intensity = 0.5 + (1 - i / snake.length) * 0.3;
                if (i % 3 === 0) fillColor = `rgba(130, 170, 100, ${intensity * 0.7})`;
                else if (i % 3 === 1) fillColor = `rgba(110, 150, 90, ${intensity * 0.7})`;
                else fillColor = `rgba(90, 130, 70, ${intensity * 0.7})`;
            }
            ctx.fillStyle = fillColor;
            roundRect(ctx, x, y, size, size, 8);
            ctx.fill();
            ctx.strokeStyle = 'rgba(210, 190, 130, 0.5)';
            ctx.lineWidth = 1.2;
            roundRect(ctx, x, y, size, size, 8);
            ctx.stroke();

            if (isHead) {
                ctx.fillStyle = '#3c2e24';
                const eyeSize = size / 6;
                let eyeX1, eyeX2, eyeY;
                if (direction === 'right') {
                    eyeX1 = x + size * 0.7;
                    eyeX2 = x + size * 0.7;
                    eyeY = y + size * 0.35;
                } else if (direction === 'left') {
                    eyeX1 = x + size * 0.3;
                    eyeX2 = x + size * 0.3;
                    eyeY = y + size * 0.35;
                } else if (direction === 'up') {
                    eyeX1 = x + size * 0.35;
                    eyeX2 = x + size * 0.65;
                    eyeY = y + size * 0.3;
                } else {
                    eyeX1 = x + size * 0.35;
                    eyeX2 = x + size * 0.65;
                    eyeY = y + size * 0.7;
                }
                ctx.beginPath();
                ctx.arc(eyeX1, eyeY, eyeSize, 0, Math.PI * 2);
                ctx.fill();
                ctx.beginPath();
                ctx.arc(eyeX2, eyeY, eyeSize, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#f9f0da';
                ctx.beginPath();
                ctx.arc(eyeX1 - 1, eyeY - 1, eyeSize * 0.3, 0, Math.PI * 2);
                ctx.fill();
                ctx.beginPath();
                ctx.arc(eyeX2 - 1, eyeY - 1, eyeSize * 0.3, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    // Отрисовка еды
    function drawFood() {
        const x = food.x * GRID_SIZE + GRID_SIZE / 2;
        const y = food.y * GRID_SIZE + GRID_SIZE / 2;
        let color, glowColor;
        if (food.type === 'normal') {
            color = '#9cba7a';
            glowColor = '#c0d192';
        } else if (food.type === 'special') {
            color = '#dbb86b';
            glowColor = '#efd28e';
        } else {
            color = '#e7d695';
            glowColor = '#fff2b5';
        }
        ctx.shadowBlur = 12;
        ctx.shadowColor = glowColor + '80';
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, GRID_SIZE / 2 - 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#fff1cf';
        ctx.beginPath();
        ctx.arc(x - 2, y - 2, GRID_SIZE / 8, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
    }

    // Основная функция отрисовки
    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawGrid();
        drawSnake();
        drawFood();
    }

    // Обновление игрового состояния
    function update() {
        if (!gameRunning || gamePaused) return;
        direction = nextDirection;
        updateDirectionIndicator();
        const head = { ...snake[0] };
        switch (direction) {
            case 'up': head.y--; break;
            case 'down': head.y++; break;
            case 'left': head.x--; break;
            case 'right': head.x++; break;
        }
        // Телепортация через границы
        if (head.x < 0) head.x = GRID_WIDTH - 1;
        if (head.x >= GRID_WIDTH) head.x = 0;
        if (head.y < 0) head.y = GRID_HEIGHT - 1;
        if (head.y >= GRID_HEIGHT) head.y = 0;

        // Проверка столкновения с собой
        for (let seg of snake) {
            if (head.x === seg.x && head.y === seg.y) {
                gameOver();
                return;
            }
        }
        snake.unshift(head);
        if (head.x === food.x && head.y === food.y) {
            let particleColor = food.type === 'normal' ? 'softgreen' : (food.type === 'special' ? 'softamber' : 'softcream');
            createParticles(head.x * GRID_SIZE + GRID_SIZE / 2, head.y * GRID_SIZE + GRID_SIZE / 2, particleColor, 20);
            if (food.type === 'special') score += 3;
            else if (food.type === 'bonus') score += 5;
            else score += 1;
            snakeLength = snake.length;
            scoreElement.textContent = score;
            lengthElement.textContent = snakeLength;
            const newLevel = Math.floor(score / 5) + 1;
            if (newLevel > level) {
                level = newLevel;
                levelElement.textContent = level;
                gameSpeed = Math.max(70, 140 - (level - 1) * 8);
                clearInterval(gameLoop);
                gameLoop = setInterval(update, gameSpeed);
                createParticles(canvas.width / 2, canvas.height / 2, 'softbrown', 30);
            }
            generateFood();
        } else {
            snake.pop();
        }
        draw();
        drawParticles();
    }

    // Обновление индикатора направления
    function updateDirectionIndicator() {
        arrows.forEach(a => a.classList.remove('active'));
        if (direction === 'up') document.querySelector('.arrow.up').classList.add('active');
        else if (direction === 'down') document.querySelector('.arrow.down').classList.add('active');
        else if (direction === 'left') document.querySelector('.arrow.left').classList.add('active');
        else if (direction === 'right') document.querySelector('.arrow.right').classList.add('active');
    }

    // Конец игры
    function gameOver() {
        gameRunning = false;
        clearInterval(gameLoop);
        for (let seg of snake) {
            createParticles(seg.x * GRID_SIZE + GRID_SIZE / 2, seg.y * GRID_SIZE + GRID_SIZE / 2, 'softbrown', 5);
        }
        finalScoreElement.textContent = score;
        finalLevelElement.textContent = level;
        finalLengthElement.textContent = snakeLength;
        gameOverScreen.style.display = 'flex';
    }

    // Пауза
    function togglePause() {
        if (!gameRunning) return;
        gamePaused = !gamePaused;
        pauseScreen.style.display = gamePaused ? 'flex' : 'none';
    }

    // Полноэкранный режим
    function toggleFullscreen() {
        if (!document.fullscreenElement) document.documentElement.requestFullscreen();
        else document.exitFullscreen();
    }

    // Обработка клавиш
    function handleKeyDown(e) {
        if (gameRunning && !gamePaused) {
            switch (e.code) {
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
        switch (e.code) {
            case 'Space':
                if (!gameRunning && startScreen.style.display !== 'none') initGame();
                else if (gameRunning) togglePause();
                e.preventDefault();
                break;
            case 'KeyP':
                if (gameRunning) togglePause();
                e.preventDefault();
                break;
            case 'KeyR':
                initGame();
                e.preventDefault();
                break;
            case 'KeyF':
                toggleFullscreen();
                e.preventDefault();
                break;
            case 'Escape':
                if (document.fullscreenElement) document.exitFullscreen();
                break;
        }
    }

    // Инициализация управления
    function initControls() {
        document.addEventListener('keydown', handleKeyDown);
        startBtn.addEventListener('click', () => {
            if (!gameRunning) initGame();
            else togglePause();
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
        window.addEventListener('resize', () => {
            initCanvasSize();
            if (gameRunning) draw();
            drawParticles();
        });
        document.addEventListener('fullscreenchange', () => {
            setTimeout(() => {
                initCanvasSize();
                if (gameRunning) draw();
                drawParticles();
            }, 100);
        });
    }

    // Анимация частиц
    function animateParticles() {
        drawParticles();
        requestAnimationFrame(animateParticles);
    }

    // Инициализация приложения
    function init() {
        initCanvasSize();
        initControls();
        animateParticles();
        startScreen.style.display = 'flex';
    }

    init();
});