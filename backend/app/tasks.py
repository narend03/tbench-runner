"""Celery tasks for executing Terminal-Bench runs."""

import os
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
import structlog

from .celery_app import celery_app
from .database import get_db_session
from .models import Task, Run, TaskStatus, RunStatus
from .harbor_runner import HarborRunner
from .config import get_settings

settings = get_settings()
logger = structlog.get_logger()


@celery_app.task(bind=True, max_retries=3)
def execute_run(self, task_id: int, run_id: int):
    """
    Execute a single run of a Terminal-Bench task.
    
    This is the atomic unit of work - one task execution.
    """
    logger.info("Starting run execution", task_id=task_id, run_id=run_id)
    
    with get_db_session() as db:
        # Get task and run from database
        task = db.query(Task).filter(Task.id == task_id).first()
        run = db.query(Run).filter(Run.id == run_id).first()
        
        if not task or not run:
            logger.error("Task or run not found", task_id=task_id, run_id=run_id)
            return {"error": "Task or run not found"}
        
        # Update run status
        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.utcnow()
        db.commit()
        
        try:
            # Create temp directory for this run
            with tempfile.TemporaryDirectory() as temp_dir:
                # Initialize runner
                runner = HarborRunner(
                    task_path=temp_dir,
                    model=task.model,
                    agent=task.agent,
                    harness=task.harness,
                    jobs_dir=os.path.join(settings.jobs_dir, str(task_id)),
                )
                
                # Extract task
                task_dir = runner.extract_task(task.file_path, temp_dir)
                runner.task_path = Path(task_dir)
                
                # Execute the run
                run_result_id = f"task_{task_id}_run_{run_id}"
                result = runner.run_single(run_result_id)
                
                # Update run with results
                run.status = (
                    RunStatus.PASSED.value if result["success"] 
                    else RunStatus.FAILED.value
                )
                run.completed_at = datetime.utcnow()
                run.tests_total = result["tests_total"]
                run.tests_passed = result["tests_passed"]
                run.tests_failed = result["tests_failed"]
                run.logs = result["logs"]
                run.error_message = result["error"]
                run.duration_seconds = result["duration_seconds"]
                run.output_path = result["output_path"]
                
                db.commit()
                
                logger.info(
                    "Run completed",
                    task_id=task_id,
                    run_id=run_id,
                    success=result["success"],
                    tests_passed=result["tests_passed"]
                )
                
                # Check if all runs are complete and update task
                update_task_status(db, task_id)
                
                return result
                
        except Exception as e:
            logger.error("Run failed with exception", error=str(e))
            run.status = RunStatus.ERROR.value
            run.completed_at = datetime.utcnow()
            run.error_message = str(e)
            db.commit()
            
            # Update task status
            update_task_status(db, task_id)
            
            raise


@celery_app.task(bind=True)
def execute_task(self, task_id: int):
    """
    Execute all runs for a task.
    
    This task spawns individual run tasks.
    """
    logger.info("Starting task execution", task_id=task_id)
    
    with get_db_session() as db:
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task:
            logger.error("Task not found", task_id=task_id)
            return {"error": "Task not found"}
        
        # Update task status
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.utcnow()
        db.commit()
        
        # Create run records
        for run_num in range(1, task.num_runs + 1):
            run = Run(
                task_id=task_id,
                run_number=run_num,
                status=RunStatus.PENDING.value,
            )
            db.add(run)
        
        db.commit()
        
        # Get all runs and spawn execution tasks
        runs = db.query(Run).filter(Run.task_id == task_id).all()
        run_ids = [run.id for run in runs]
    
    # Spawn individual run tasks (outside of db session)
    for run_id in run_ids:
        execute_run.delay(task_id, run_id)
    
    logger.info("Spawned run tasks", task_id=task_id, num_runs=len(run_ids))
    
    return {"task_id": task_id, "runs_spawned": len(run_ids)}


def update_task_status(db, task_id: int):
    """Update task status based on completed runs."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
    
    runs = db.query(Run).filter(Run.task_id == task_id).all()
    
    # Count completed runs
    completed_runs = [r for r in runs if r.status not in [RunStatus.PENDING.value, RunStatus.RUNNING.value]]
    passed_runs = [r for r in runs if r.status == RunStatus.PASSED.value]
    failed_runs = [r for r in runs if r.status in [RunStatus.FAILED.value, RunStatus.ERROR.value]]
    
    # Update task counts
    task.total_runs = len(runs)
    task.passed_runs = len(passed_runs)
    task.failed_runs = len(failed_runs)
    
    # Update status if all runs complete
    if len(completed_runs) == len(runs):
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = datetime.utcnow()
    
    db.commit()

