#!/usr/bin/env bash
set -e

# ждём БД 
DBH="${DB_HOST:-${POSTGRES_HOST}}"
DBP="${DB_PORT:-${POSTGRES_PORT:-3333}}"

if [ -n "${DBH}" ]; then
  echo "Waiting for Postgres at ${DBH}:${DBP}..."
  for i in {1..60}; do
    (echo > /dev/tcp/${DBH}/${DBP}) >/dev/null 2>&1 && break
    sleep 1
  done
fi

cd /app/src

# миграции для django-tenants
python manage.py migrate_schemas --shared --noinput
# при необходимости можно мигрировать и тенантов (когда они уже созданы)
# python manage.py migrate_schemas --executor tenant --noinput || true

# собрать статику
python manage.py collectstatic --noinput

gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
