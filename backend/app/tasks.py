"""Celery tasks for async Harbor execution."""

from datetime import datetime
from celery import shared_task
from sqlalchemy.orm import Session

from .celery_app import celery_app
from .database import SessionLocal
from .models import Task, Run, TaskStatus, RunStatus
from .harbor_runner import run_task_sync
from .config import get_settings

settings = get_settings()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
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
        
        print(f"🏃 Celery executing run {run_id} for task {task_id}...")
        
        # Execute Harbor
        result = run_task_sync(
            zip_path=task.file_path,
            model=task.model,
            agent=task.agent,
            openrouter_api_key=openrouter_api_key,
            run_id=f"task_{task_id}_run_{run_id}",
            timeout_seconds=timeout_seconds,
        )
        
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
def execute_all_runs(
    task_id: int,
    openrouter_api_key: str,
    timeout_seconds: int = 1200,
):
    """
    Queue all runs for a task.
    
    This creates the runs and dispatches them to workers.
    """
    db = SessionLocal()
    
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
        
        print(f"▶️ Celery queuing {task.num_runs} runs for task {task_id}")
        
        # Queue each run as a separate Celery task
        for run_id in run_ids:
            execute_harbor_run.delay(
                task_id=task_id,
                run_id=run_id,
                openrouter_api_key=openrouter_api_key,
                timeout_seconds=timeout_seconds,
            )
        
        return {
            "task_id": task_id,
            "runs_queued": len(run_ids),
            "run_ids": run_ids,
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
