#!/usr/bin/env sh
set -eu
python manage.py migrate --noinput
exec gunicorn Shopphi.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 2 --timeout 120
