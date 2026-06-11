#!/bin/bash
set -e

echo "Starting development environment..."

if [ ! -f .env ]; then
    echo "Error: .env not found. Run ./setup.sh first."
    exit 1
fi

source .venv/bin/activate

export $(grep -v '^#' .env | xargs)

echo "Starting API server..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
