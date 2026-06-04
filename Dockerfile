FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    POETRY_VERSION=2.1.0

# Системные зависимости
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

# Установка Poetry
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"
RUN poetry config virtualenvs.create false  # Устанавливаем пакеты в систему

WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock* ./

# Создаём README.md, если его нет (poetry требует)
RUN if [ ! -f README.md ]; then echo "# RanhRasp" > README.md; fi

# Устанавливаем только зависимости (без самого проекта)
RUN poetry install --no-root --no-interaction --no-ansi

# Копируем весь код
COPY . .

# Устанавливаем браузер Playwright
RUN playwright install chromium

CMD ["python", "main.py"]