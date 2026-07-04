document.addEventListener('DOMContentLoaded', () => {
    const loadRandomBackground = async () => {
        try {
            // Absolute path ensures it doesn't break on deep wildcard URLs
            const response = await fetch('/toadcode/api/backgrounds');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();
            const backgrounds = data.backgrounds;
            if (!backgrounds || backgrounds.length === 0) return;

            const selectedBackground = backgrounds[Math.floor(Math.random() * backgrounds.length)];
            const videoElement = document.querySelector('.gif-background');
            if (!videoElement) return;

            videoElement.innerHTML = '';
            const source = document.createElement('source');
            source.src = `https://cdn.jsdelivr.net/gh/Nergan/media@main/toadcode/backgrounds/${selectedBackground}`;
            source.type = 'video/mp4';
            videoElement.appendChild(source);

            videoElement.autoplay = true; videoElement.loop = true;
            videoElement.muted = true; videoElement.playsInline = true;
            videoElement.load();
        } catch (error) {
            console.error('Error loading background list:', error);
        }
    };
    loadRandomBackground();
});