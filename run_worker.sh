#!/bin/bash
set -e

source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

echo "Starting Celery worker..."
celery -A app.celery_app worker --loglevel=info --concurrency=2
