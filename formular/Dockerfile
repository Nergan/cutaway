FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    libreoffice-core libreoffice-writer libreoffice-calc \
    pandoc ffmpeg p7zip-full unrar-free libcairo2-dev djvulibre-bin \
    libmagic1 curl wget fonts-liberation fonts-dejavu libreoffice-impress && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright and its underlying system dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .
EXPOSE 8000
CMD ["python", "main.py", "--web"]