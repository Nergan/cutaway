FROM python:3.11-slim

ARG CUTAWAY_PROFILE=hf
ARG CUTAWAY_ISOLATION=isolated

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/home/user/pw-browsers
ENV CUTAWAY_PROFILE=${CUTAWAY_PROFILE}
ENV CUTAWAY_ISOLATION=${CUTAWAY_ISOLATION}
ENV CUTAWAY_REQUIRE_VENVS=1
ENV CUTAWAY_VENV_ROOT=/app/.orchestrator/venvs
ENV CUTAWAY_RUNTIME_DIR=/tmp/cutaway-runtime

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
# HF builder часто роняет сборку на одном медленном GET к PyPI. Не гоняем
# `pip install --upgrade pip`: в образе уже есть рабочий pip, а обрыв на
# files.pythonhosted.org из-за `&&` раньше даже не давал запустить build.sh.
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_RETRIES=10
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy the entire repository first to allow plugin discovery during build
COPY --chown=user . .

# 1. СНАЧАЛА исправляем концы строк (CRLF -> LF)
RUN sed -i 's/\r$//' start.sh build.sh && chmod +x build.sh start.sh

# 2. И ТОЛЬКО ПОТОМ запускаем сборку
RUN ./build.sh

# Project code and isolated environments are immutable at runtime. Projects
# receive separate writable HOME/TMP/cache directories below CUTAWAY_RUNTIME_DIR.
USER root
RUN mkdir -p "$CUTAWAY_RUNTIME_DIR" \
    && chown user:user "$CUTAWAY_RUNTIME_DIR" \
    && chmod 700 "$CUTAWAY_RUNTIME_DIR" \
    && chmod -R a-w /app
USER user

EXPOSE 7860

# Execute standard start.sh instead of directly invoking uvicorn to allow background task boot
CMD ["./start.sh"]