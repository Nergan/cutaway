# syntax=docker/dockerfile:1
#
# Контейнеризуется только бот (bot/main.py) — он единственный компонент
# этого пакета, которому нужен постоянно работающий процесс (long-polling).
# CLI (cli/main.py) — ad-hoc инструмент администратора, обычно запускается
# локально через `pip install -e .` (см. README.md), контейнер ему не нужен.

FROM python:3.12-slim AS base

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY another_admin/ ./another_admin/

RUN useradd --create-home --uid 10001 botuser
USER botuser

ENTRYPOINT ["python", "-m", "another_admin.bot.main"]
