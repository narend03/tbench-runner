#!/bin/bash
# Start Celery worker and beat in the same container
# Beat publishes queue metrics every 60 seconds

# Start Beat in background
echo "⏰ Starting Celery Beat (for periodic metrics)..."
celery -A app.celery_app beat --loglevel=info &
BEAT_PID=$!

# Start Worker in foreground
echo "🚀 Starting Celery worker..."
celery -A app.celery_app worker --loglevel=info --concurrency=4 -Q celery,harbor

# If worker exits, kill beat
kill $BEAT_PID 2>/dev/null

