"""Celery application configuration for async task execution."""

from celery import Celery
from .config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "tbench_runner",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],  # Import tasks module
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Don't prefetch tasks (Harbor is slow)
    worker_concurrency=4,  # 4 concurrent Harbor runs per worker
    
    # Task execution settings
    task_acks_late=True,  # Ack after task completes (for reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    
    # Retry settings
    task_default_retry_delay=60,  # Wait 60s before retry
    task_max_retries=2,  # Max 2 retries
)

# Optional: Configure task routes for different queues
celery_app.conf.task_routes = {
    "app.tasks.execute_harbor_run": {"queue": "harbor"},
}
