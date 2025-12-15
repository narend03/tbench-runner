"""Celery tasks for async Harbor execution."""

from datetime import datetime
from celery import shared_task
from sqlalchemy.orm import Session

from .celery_app import celery_app
from .database import SessionLocal
from .models import Task, Run, TaskStatus, RunStatus
from .harbor_runner import run_task_sync
from .config import get_settings
from .cloudwatch_metrics import publish_queue_depth_metric

settings = get_settings()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    time_limit=1500,  # Hard limit: 25 minutes (kills task if still running)
    soft_time_limit=1200,  # Soft limit: 20 minutes (raises SoftTimeLimitExceeded)
)
def execute_harbor_run(
    self,
    task_id: int,
    run_id: int,
    openrouter_api_key: str,
    timeout_seconds: int = 1200,
):
    """
    Execute a single Harbor run asynchronously.
    
    This task is called by Celery workers in the background.
    Includes retry logic for transient Docker/file mounting errors.
    """
    db = SessionLocal()
    
    try:
        # Get task and run from database
        task = db.query(Task).filter(Task.id == task_id).first()
        run = db.query(Run).filter(Run.id == run_id).first()
        
        if not task or not run:
            print(f"❌ Task {task_id} or Run {run_id} not found")
            return {"error": "Task or run not found"}
        
        # Update run status to running
        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.utcnow()
        db.commit()
        
        print(f"🏃 Celery executing run {run_id} for task {task_id} (attempt {self.request.retries + 1})...")
        
        # Get file (downloads from S3 if needed)
        from .storage import get_file
        local_zip_path = get_file(task.file_path)
        if not local_zip_path:
            raise FileNotFoundError(f"Could not get file: {task.file_path}")
        
        print(f"📦 Extracted task to: {local_zip_path}")
        
        # Execute Harbor
        result = run_task_sync(
            zip_path=local_zip_path,
            model=task.model,
            agent=task.agent,
            openrouter_api_key=openrouter_api_key,
            run_id=f"task_{task_id}_run_{run_id}",
            timeout_seconds=timeout_seconds,
        )
        
        # Check for transient Docker/file errors that should trigger retry
        logs = result.get("logs", "") or ""
        is_transient_error = (
            "No such file or directory" in logs or
            "/tests/test.sh" in logs and "not found" in logs.lower() or
            "cannot set terminal process group" in logs
        )
        
        if is_transient_error and not result["success"] and self.request.retries < self.max_retries:
            print(f"⚠️ Run {run_id} hit transient error, retrying...")
            # Reset run status for retry
            run.status = RunStatus.PENDING.value
            run.started_at = None
            db.commit()
            raise self.retry(countdown=10)  # Retry after 10 seconds
        
        # Update run with results
        run.status = RunStatus.PASSED.value if result["success"] else RunStatus.FAILED.value
        run.completed_at = datetime.utcnow()
        run.tests_total = result["tests_total"]
        run.tests_passed = result["tests_passed"]
        run.tests_failed = result["tests_failed"]
        run.logs = result["logs"][:50000] if result["logs"] else None
        run.error_message = result["error"]
        run.duration_seconds = result["duration_seconds"]
        
        db.commit()
        
        # Update task statistics
        _update_task_stats(db, task)
        
        print(f"✅ Celery run {run_id} completed: {'PASSED' if result['success'] else 'FAILED'}")
        
        return {
            "run_id": run_id,
            "task_id": task_id,
            "status": run.status,
            "success": result["success"],
            "tests_passed": result["tests_passed"],
            "tests_total": result["tests_total"],
        }
        
    except Exception as e:
        print(f"❌ Celery run {run_id} failed: {e}")
        
        # Mark run as error
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = RunStatus.ERROR.value
                run.completed_at = datetime.utcnow()
                run.error_message = str(e)
                db.commit()
                
                task = db.query(Task).filter(Task.id == task_id).first()
                if task:
                    _update_task_stats(db, task)
        except:
            pass
        
        # Retry on transient errors
        raise self.retry(exc=e)
        
    finally:
        db.close()


@celery_app.task
def publish_queue_metrics():
    """
    Periodic task to publish queue depth metrics to CloudWatch.
    
    This enables auto-scaling based on queue depth rather than just CPU.
    Should be called every 60 seconds via Celery Beat.
    """
    try:
        publish_queue_depth_metric()
    except Exception as e:
        print(f"⚠️  Failed to publish queue metrics: {e}")


@celery_app.task
def execute_all_runs(
    task_id: int,
    openrouter_api_key: str,
    timeout_seconds: int = 1200,
):
    """
    Queue all runs for a task with staggered starts.
    
    This creates the runs and dispatches them to workers with small delays
    between batches to prevent Docker container race conditions.
    """
    db = SessionLocal()
    
    # Stagger configuration
    BATCH_SIZE = 20  # Start 20 runs at a time
    BATCH_DELAY_SECONDS = 1  # 1 second delay between batches
    
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task:
            return {"error": "Task not found"}
        
        if task.status != TaskStatus.PENDING.value:
            return {"error": f"Task is already {task.status}"}
        
        # Update task status
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.utcnow()
        
        # Create runs
        run_ids = []
        for run_num in range(1, task.num_runs + 1):
            run = Run(
                task_id=task.id,
                run_number=run_num,
                status=RunStatus.PENDING.value,
            )
            db.add(run)
            db.flush()  # Get the run ID
            run_ids.append(run.id)
        
        task.total_runs = task.num_runs
        db.commit()
        
        print(f"▶️ Celery queuing {task.num_runs} runs for task {task_id} (staggered, {BATCH_SIZE} per batch)")
        
        # Queue each run with staggered start times
        # This prevents Docker container race conditions at scale
        for i, run_id in enumerate(run_ids):
            # Calculate delay: runs in same batch start together
            # Batch 0 (runs 0-19): delay 0s
            # Batch 1 (runs 20-39): delay 1s
            # Batch 2 (runs 40-59): delay 2s
            batch_number = i // BATCH_SIZE
            delay_seconds = batch_number * BATCH_DELAY_SECONDS
            
            execute_harbor_run.apply_async(
                kwargs={
                    "task_id": task_id,
                    "run_id": run_id,
                    "openrouter_api_key": openrouter_api_key,
                    "timeout_seconds": timeout_seconds,
                },
                countdown=delay_seconds,
            )
        
        total_stagger_time = ((len(run_ids) - 1) // BATCH_SIZE) * BATCH_DELAY_SECONDS
        print(f"📊 Stagger complete: {len(run_ids)} runs queued over {total_stagger_time}s")
        
        return {
            "task_id": task_id,
            "runs_queued": len(run_ids),
            "run_ids": run_ids,
            "stagger_seconds": total_stagger_time,
        }
        
    finally:
        db.close()


def _update_task_stats(db: Session, task: Task):
    """Update task statistics based on completed runs."""
    runs = db.query(Run).filter(Run.task_id == task.id).all()
    
    completed_statuses = [RunStatus.PASSED.value, RunStatus.FAILED.value, RunStatus.ERROR.value]
    completed_runs = [r for r in runs if r.status in completed_statuses]
    passed_runs = [r for r in runs if r.status == RunStatus.PASSED.value]
    failed_runs = [r for r in runs if r.status in [RunStatus.FAILED.value, RunStatus.ERROR.value]]
    
    task.total_runs = len(runs)
    task.passed_runs = len(passed_runs)
    task.failed_runs = len(failed_runs)
    
    # Mark task complete if all runs done
    if len(completed_runs) >= task.num_runs:
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = datetime.utcnow()
    
    db.commit()
