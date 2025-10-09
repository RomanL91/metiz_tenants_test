FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# системные зависимости (psycopg, pillow и т.п.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# ставим Poetry
RUN pip install "poetry==1.8.*" && poetry --version

# чтобы poetry ставил пакеты в системное окружение контейнера (без venv)
RUN poetry config virtualenvs.create false

# сперва только спецификации — это ускоряет кеш
COPY pyproject.toml poetry.lock* /app/

# прод-вариант: только основные зависимости
# dev-вариант: --with dev (если у тебя есть [tool.poetry.group.dev])
ARG POETRY_WITH=
RUN if [ -n "$POETRY_WITH" ]; then \
    poetry install --no-interaction --no-ansi --no-root --with "$POETRY_WITH"; \
    else \
    poetry install --no-interaction --no-ansi --no-root --only main; \
    fi

# исходники
COPY src/ /app/src/

# entrypoint
COPY /entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
