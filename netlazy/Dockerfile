# ---------- Stage 1: Build the Vue/Vite frontend ----------
FROM node:20-alpine AS frontend-builder

WORKDIR /build

COPY package.json package-lock.json vite.config.js ./
COPY frontend ./frontend

RUN npm ci

# vite.config.js sets root:'frontend' and build.outDir:'../backend/static',
# so this writes static assets to /build/backend/static
RUN npm run build


# ---------- Stage 2: Python runtime ----------
FROM python:3.11-slim

# ffmpeg    -> required by app/infrastructure/media_processor.py (image/video/audio transcoding)
# libmagic1 -> required by python-magic for MIME sniffing in media_processor.py
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY --from=frontend-builder /build/backend/static ./backend/static

# Run as a non-root user
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# app.main:app is imported as the "app" package inside backend/, so this
# must be the working directory the process runs from
WORKDIR /app/backend

# Hugging Face Spaces (Docker SDK) routes external traffic to port 7860
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]