FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Poetry — ставим в system site-packages (без отдельных venv),
    # чтобы entrypoint мог звать "python manage.py …" без "poetry run".
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# системные зависимости для psycopg2 и nc
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev netcat-traditional curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry в системное окружение
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Сначала только манифесты зависимостей — максимально кешируем слой
COPY pyproject.toml poetry.lock* /app/
# Ставим зависимости проекта (без установки самого проекта, т.е. --no-root)
# Если нужны dev-зависимости — добавь:  --with dev
RUN poetry install --no-root --no-ansi

# Теперь весь код
COPY . /app

# Папки под статику и медиа (совпадают с Django settings)
RUN mkdir -p /app/staticfiles /app/media

# entrypoint кладём вне /app, чтобы volume с кодом его не «перекрыл»
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
