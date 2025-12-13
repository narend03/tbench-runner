#!/bin/bash
# Start Celery worker for TBench Runner

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment variables
export OPENAI_API_BASE="https://api.openai.com/v1"

# Add harbor to PATH
export PATH="$HOME/.local/bin:$PATH"

# Start Celery worker
echo "🚀 Starting Celery worker..."
celery -A app.celery_app worker --loglevel=info --concurrency=4 -Q celery,harbor

