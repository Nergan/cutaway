document.addEventListener('DOMContentLoaded', () => {
    const loadRandomBackground = async () => {
        try {
            const response = await fetch('./api/backgrounds');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const backgrounds = data.backgrounds;

            if (!backgrounds || backgrounds.length === 0) {
                console.warn('No background videos found on server');
                return;
            }

            const randomIndex = Math.floor(Math.random() * backgrounds.length);
            const selectedBackground = backgrounds[randomIndex];

            const videoElement = document.querySelector('.gif-background');
            if (!videoElement) {
                console.warn('Video element with class .gif-background not found');
                return;
            }

            // Clear previous sources and add new one
            videoElement.innerHTML = '';
            const source = document.createElement('source');
            source.src = `/toadbin/static/backgrounds/${selectedBackground}`;
            source.type = 'video/mp4';
            videoElement.appendChild(source);

            // Ensure required attributes
            videoElement.autoplay = true;
            videoElement.loop = true;
            videoElement.muted = true; // required for autoplay
            videoElement.playsInline = true; // for mobile devices

            videoElement.load();

            // Error handling for video load failure
            videoElement.onerror = () => {
                console.warn(`Failed to load video: ${selectedBackground}`);
                // Try another random background as fallback
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
            // Fallback to a default video
            const videoElement = document.querySelector('.gif-background');
            if (videoElement) {
                videoElement.innerHTML = '';
                const source = document.createElement('source');
                source.src = '/toadbin/static/backgrounds/there is no god beyond.mp4';
                source.type = 'video/mp4';
                videoElement.appendChild(source);
                videoElement.load();
            }
        }
    };

    loadRandomBackground();
});