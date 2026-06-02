# Используем официальный образ Python 3.12 slim
FROM python:3.12-slim

# Устанавливаем переменные окружения для Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Устанавливаем системные зависимости:
# - gcc, libpq-dev: для psycopg2 / asyncpg (хотя asyncpg не требует компиляции, но оставим)
# - Зависимости Playwright (Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm-dev \
    libgbm-dev \
    libasound2 \
    libxkbcommon-dev \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml ./

# Устанавливаем Python-пакеты (поддерживает pyproject.toml без setup.py)
RUN pip install --no-cache-dir .

# Копируем остальной код проекта
COPY . .

# Устанавливаем браузер Chromium для Playwright
RUN playwright install chromium

# Команда запуска
CMD ["python", "main.py"]
