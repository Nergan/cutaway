FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

RUN apt-get update && apt-get install -y xvfb && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright and its dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .
EXPOSE 8000
# Run Xvfb in the background, then launch Uvicorn
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & python main.py --web"]