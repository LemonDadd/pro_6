#!/bin/bash
set -e

echo "=== Markdown to PDF API Setup ==="

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your configuration values."
fi

if [ ! -d .venv ]; then
    echo "Creating Python virtual environment..."
    python3.11 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start the development server:"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "To start Celery worker:"
echo "  source .venv/bin/activate"
echo "  celery -A app.celery_app worker --loglevel=info"
echo ""
echo "Make sure Redis and MinIO are running, or use docker-compose:"
echo "  docker-compose up -d redis minio kroki"
