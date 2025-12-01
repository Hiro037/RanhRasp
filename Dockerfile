FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium

COPY pyproject.toml poetry.lock* ./

RUN pip install --upgrade pip wheel poetry

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY . .

RUN playwright install --with-deps chromium

EXPOSE 8000