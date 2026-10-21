#!/usr/bin/env bash
# Build step used by the host (Render etc.): install, collect static files, migrate.
set -o errexit
pip install -r requirements-prod.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py ensure_admin
python manage.py seed_demo --if-demo
