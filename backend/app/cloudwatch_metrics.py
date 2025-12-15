"""CloudWatch metrics for auto-scaling based on queue depth."""

import os
import boto3
from typing import Optional

# Lazy import celery to avoid circular imports
try:
    from celery import current_app
except ImportError:
    current_app = None

# Initialize CloudWatch client (lazy)
_cloudwatch_client: Optional[boto3.client] = None


def get_cloudwatch_client():
    """Get or create CloudWatch client."""
    global _cloudwatch_client
    if _cloudwatch_client is None:
        _cloudwatch_client = boto3.client(
            'cloudwatch',
            region_name=os.getenv('AWS_REGION', 'us-west-2')
        )
    return _cloudwatch_client


def get_celery_queue_depth() -> int:
    """
    Get the current depth of the Celery queue.
    
    Returns the total number of tasks waiting to be processed.
    Uses Redis directly to get accurate queue length.
    """
    try:
        import redis
        from .config import get_settings
        
        settings = get_settings()
        
        # Parse Redis URL
        redis_url = settings.redis_url.replace("redis://", "")
        if "/" in redis_url:
            host_port, db = redis_url.split("/")
        else:
            host_port, db = redis_url, "0"
        
        if ":" in host_port:
            host, port = host_port.split(":")
        else:
            host, port = host_port, "6379"
        
        # Connect to Redis and get queue length
        r = redis.Redis(host=host, port=int(port), db=int(db), decode_responses=True)
        
        # Get length of Celery queues
        # Celery uses these keys: celery, harbor (from task_routes)
        queue_length = 0
        for queue_name in ["celery", "harbor"]:
            try:
                length = r.llen(queue_name)
                if length:
                    queue_length += length
            except Exception:
                pass  # Queue might not exist yet
        
        return queue_length
        
    except Exception as e:
        # Fallback: try Celery inspect (less reliable, but works if Redis fails)
        try:
            if current_app is None:
                return 0
            inspect = current_app.control.inspect()
            if inspect is None:
                return 0
            active = inspect.active() or {}
            scheduled = inspect.scheduled() or {}
            reserved = inspect.reserved() or {}
            
            total_tasks = 0
            for worker_tasks in active.values():
                total_tasks += len(worker_tasks)
            for worker_tasks in scheduled.values():
                total_tasks += len(worker_tasks)
            for worker_tasks in reserved.values():
                total_tasks += len(worker_tasks)
            
            return total_tasks
        except Exception as e2:
            # If we can't get queue depth, return 0 (don't break the app)
            print(f"⚠️  Could not get Celery queue depth: {e}, {e2}")
            return 0


def publish_queue_depth_metric():
    """
    Publish Celery queue depth to CloudWatch.
    
    This metric is used by AWS Auto Scaling to scale workers based on
    actual queue depth rather than just CPU usage.
    """
    try:
        queue_depth = get_celery_queue_depth()
        
        # Publish to CloudWatch
        cloudwatch = get_cloudwatch_client()
        cloudwatch.put_metric_data(
            Namespace='TBench/Celery',
            MetricData=[{
                'MetricName': 'QueueDepth',
                'Value': queue_depth,
                'Unit': 'Count',
                'Timestamp': None,  # Use current time
            }]
        )
        
        print(f"📊 Published queue depth metric: {queue_depth} tasks")
        return queue_depth
        
    except Exception as e:
        # Don't break the app if CloudWatch fails
        print(f"⚠️  Could not publish queue depth metric: {e}")
        return None
