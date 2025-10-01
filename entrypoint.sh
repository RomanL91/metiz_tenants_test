#!/usr/bin/env bash
set -e

echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until nc -z "${POSTGRES_HOST}" "${POSTGRES_PORT}"; do
  sleep 0.5
done
echo "Postgres is up."

echo "Running migrate_schemas..."
python manage.py migrate_schemas --shared --noinput || true
python manage.py migrate_schemas --noinput || true

echo "Collecting static..."
python manage.py collectstatic --noinput

echo "Starting Django on 0.0.0.0:8000 ..."
python manage.py runserver 0.0.0.0:8000
