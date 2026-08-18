# ---------- Stage 1: Build the Vue/Vite frontend ----------
FROM node:20-alpine AS frontend-builder

WORKDIR /build

COPY package.json package-lock.json* vite.config.js ./
COPY frontend ./frontend

RUN npm ci
RUN npm run build


# ---------- Stage 2: Python runtime ----------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./netlazy
COPY --from=frontend-builder /build/static ./netlazy/static

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 7860

CMD ["uvicorn", "netlazy.main:app", "--host", "0.0.0.0", "--port", "7860"]