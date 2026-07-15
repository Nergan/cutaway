FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/home/user/pw-browsers

# Enable non-free repositories to allow installation of unrar and p7zip-rar
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's/Components: .*/& contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i 's/ main/ main contrib non-free non-free-firmware/g' /etc/apt/sources.list; \
    fi

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    curl \
    libreoffice-core \
    libreoffice-writer \
    libreoffice-calc \
    pandoc \
    ffmpeg \
    p7zip-full \
    p7zip-rar \
    unrar \
    libcairo2-dev \
    djvulibre-bin \
    libreoffice-impress \
    libmagic1 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user

ENV PATH="/home/user/.local/bin:$PATH"
ENV DISPLAY=:99

WORKDIR /app

# Copy the entire repository first to allow plugin discovery during build
COPY --chown=user . .

# 1. СНАЧАЛА исправляем концы строк (CRLF -> LF)
RUN sed -i 's/\r$//' start.sh build.sh && chmod +x build.sh start.sh

# 2. И ТОЛЬКО ПОТОМ запускаем сборку
RUN pip install --no-cache-dir --upgrade pip && ./build.sh

EXPOSE 7860

# Execute standard start.sh instead of directly invoking uvicorn to allow background task boot
CMD ["./start.sh"]