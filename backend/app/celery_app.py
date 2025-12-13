"""Celery application for distributed task execution."""

from celery import Celery
from .config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "tbench_runner",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"]
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_concurrency=4,  # Number of concurrent workers
    
    # Result settings
    result_expires=86400,  # 24 hours
    
    # Task limits
    task_time_limit=7200,  # 2 hours max per task
    task_soft_time_limit=3600,  # 1 hour soft limit
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Rate limiting for API calls
    task_default_rate_limit="10/m",
)

# Task routing
celery_app.conf.task_routes = {
    "app.tasks.execute_run": {"queue": "runs"},
    "app.tasks.execute_task": {"queue": "tasks"},
}

