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
    curl \
    wget \
    git \
    xvfb \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libatspi2.0-0 \
    libgtk-3-0 \
    ca-certificates \
    fonts-liberation \
    fonts-dejavu \
    libreoffice-core \
    libreoffice-writer \
    libreoffice-calc \
    libmagic1 \
    pandoc \
    ffmpeg \
    p7zip-full \
    p7zip-rar \
    unrar \
    libcairo2-dev \
    djvulibre-bin \
    libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user

ENV PATH="/home/user/.local/bin:$PATH"
ENV DISPLAY=:99

WORKDIR /app
COPY --chown=user requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY --chown=user . .
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]