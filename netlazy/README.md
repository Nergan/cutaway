# netlazy

[Читать на русском (README.ru.md)](./README.ru.md)

`netlazy` is an independent dating and networking application designed to operate without reliance on external identity providers, SMS gateways, or email verification services. Authentication is managed entirely through client-side generated key pairs and cryptographic signatures, ensuring a self-contained system.

---

## Key Features

*   **Independent Authentication**: Users generate a 2048-bit RSA key pair locally. Requests are authenticated using HTTP signatures instead of passwords or third-party OAuth (e.g., Google or Apple logins), keeping the application completely autonomous.
*   **On-the-Fly Media Obfuscation**: Uploaded media (images, video, and audio) is stored as a low-resolution public cover appended with an encrypted payload. The original file is decrypted on-the-fly by the viewing client, preventing direct scraping of raw files from the storage CDN.
*   **Proof of Work Rate-Limiting**: To prevent registration floods and spam without relying on third-party CAPTCHA services, the platform requires clients to solve a cryptographic challenge (Proof of Work) before performing sensitive state changes.
*   **Handshake Matching System**: Mutual consent is established using progressive "handshakes" (Share, Exchange, Demand, and Mutual) to negotiate how and when private contact details are revealed.

---

## Directory Overview

*   `domain/` — Core business models and repository abstractions.
*   `application/` — Use case services handling authentication, profile updates, and handshakes.
*   `infrastructure/` — MongoDB repositories, CDN storage integration, and media processing.
*   `presentation/` — FastAPI routers and cryptographic request signature validation.
*   `frontend/` — Client-side SPA built with Vue 3 and Vite, configured for optional Capacitor native app builds.