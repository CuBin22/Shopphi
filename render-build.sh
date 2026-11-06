#!/usr/bin/env sh
set -eu
pip install -r requirements.txt
python manage.py collectstatic --noinput
