"""FastAPI main application for TBench Runner."""

import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import get_settings, AVAILABLE_MODELS, AVAILABLE_AGENTS
from .database import get_db, create_tables
from .models import (
    Task, Run, TaskStatus, RunStatus,
    TaskResponse, TaskDetailResponse, RunResponse,
    ModelsResponse, AgentsResponse
)
from .harbor_runner import run_task_sync
from .tasks import execute_harbor_run, execute_all_runs
from .cloudwatch_metrics import publish_queue_depth_metric

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="TBench Runner",
    description="Run Terminal-Bench tasks at scale with Harbor",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """Initialize application on startup."""
    # Create database tables
    create_tables()
    
    # Ensure directories exist
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.jobs_dir).mkdir(parents=True, exist_ok=True)
    
    # Start background task to publish queue metrics every 60 seconds
    import asyncio
    asyncio.create_task(publish_metrics_periodically())
    
    print(f"🚀 TBench Runner started on http://{settings.host}:{settings.port}")


async def publish_metrics_periodically():
    """Background task to publish queue depth metrics every 60 seconds."""
    import asyncio
    while True:
        try:
            # Publish metrics (runs in thread pool since it's sync)
            import concurrent.futures
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await loop.run_in_executor(pool, publish_queue_depth_metric)
        except Exception as e:
            print(f"⚠️  Failed to publish metrics: {e}")
        
        # Wait 60 seconds before next publish
        await asyncio.sleep(60)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "TBench Runner",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============== Models and Agents ==============

@app.get("/api/models", response_model=List[ModelsResponse])
async def get_models():
    """Get available models for task execution."""
    return AVAILABLE_MODELS


@app.get("/api/agents", response_model=List[AgentsResponse])
async def get_agents():
    """Get available agents/harnesses for task execution."""
    return AVAILABLE_AGENTS


# ============== Task CRUD ==============

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(
    file: UploadFile = File(...),
    name: str = Query(..., description="Task name"),
    model: str = Query("openai/gpt-5", description="Model to use"),
    agent: str = Query("terminus-2", description="Agent to use"),
    harness: str = Query("harbor", description="Harness to use"),
    num_runs: int = Query(10, ge=1, le=100, description="Number of runs"),
    db: Session = Depends(get_db),
):
    """
    Upload a new Terminal-Bench task for execution.
    
    The task should be a zip file containing:
    - task.toml: Task configuration
    - instruction.md: Task instructions
    - tests/: Test directory
    - solution/: Oracle solution (optional)
    - environment/: Environment files (optional)
    """
    # Validate file type
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a zip archive")
    
    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > settings.max_upload_size:
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Maximum size is {settings.max_upload_size // (1024*1024)}MB"
        )
    
    # Generate unique ID and save file (uses S3 in production)
    task_uuid = str(uuid.uuid4())
    
    try:
        from .storage import save_upload
        file_path = save_upload(file.file, file.filename, task_uuid)
        print(f"📁 File saved to: {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Create task record
    task = Task(
        name=name,
        original_filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        model=model,
        agent=agent,
        harness=harness,
        num_runs=num_runs,
        status=TaskStatus.PENDING.value,
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    print(f"📦 Task created: {task.id} - {name} ({num_runs} runs with {model})")
    
    # Stage 2: Just store the task, don't execute yet
    # In Stage 3, we'll add: execute_task(task.id)
    
    return task


@app.get("/api/tasks", response_model=List[TaskResponse])
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all tasks with optional filtering."""
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
    
    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return tasks


@app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a task including all runs."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a task and all associated runs."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Delete uploaded file (handles S3 and local)
    try:
        from .storage import delete_file
        delete_file(task.file_path)
    except Exception as e:
        print(f"⚠️ Failed to delete task files: {e}")
    
    # Delete task (cascades to runs)
    db.delete(task)
    db.commit()
    
    print(f"🗑️ Task deleted: {task_id}")
    return {"message": "Task deleted successfully"}


@app.post("/api/tasks/{task_id}/start")
async def start_task(task_id: int, db: Session = Depends(get_db)):
    """
    Start execution of a task.
    
    Stage 2: This is a mock - just changes status to 'running'.
    Stage 3: Will actually execute Harbor.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Task is already {task.status}")
    
    # Update status to running
    task.status = TaskStatus.RUNNING.value
    task.started_at = datetime.utcnow()
    
    # Create placeholder runs
    for run_num in range(1, task.num_runs + 1):
        run = Run(
            task_id=task.id,
            run_number=run_num,
            status=RunStatus.PENDING.value,
        )
        db.add(run)
    
    task.total_runs = task.num_runs
    db.commit()
    
    print(f"▶️ Task started: {task_id} ({task.num_runs} runs queued)")
    
    # Stage 2: Mock - just create runs with pending status
    # Stage 3: Will trigger actual Harbor execution
    
    return {"message": f"Task started with {task.num_runs} runs", "task_id": task_id}


@app.post("/api/tasks/{task_id}/retry")
async def retry_task(task_id: int, db: Session = Depends(get_db)):
    """Retry a failed or completed task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
        raise HTTPException(status_code=400, detail="Task must be completed or failed to retry")
    
    # Delete existing runs
    db.query(Run).filter(Run.task_id == task_id).delete()
    
    # Reset task status
    task.status = TaskStatus.PENDING.value
    task.started_at = None
    task.completed_at = None
    task.total_runs = 0
    task.passed_runs = 0
    task.failed_runs = 0
    
    db.commit()
    
    print(f"🔄 Task reset for retry: {task_id}")
    return {"message": "Task reset for retry", "task_id": task_id}


# ============== Execution Endpoints (Stage 3) ==============

@app.post("/api/tasks/{task_id}/runs/{run_id}/execute")
def execute_run(
    task_id: int,
    run_id: int,
    openrouter_api_key: str = Query(..., description="OpenRouter API key"),
    timeout_seconds: int = Query(1200, description="Timeout in seconds"),
    db: Session = Depends(get_db),
):
    """
    Execute a single run synchronously using Harbor.
    
    This endpoint blocks until Harbor completes (or times out).
    Returns the full results including logs and test counts.
    """
    # Get task and run
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    run = db.query(Run).filter(Run.id == run_id, Run.task_id == task_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if run.status not in [RunStatus.PENDING.value]:
        raise HTTPException(status_code=400, detail=f"Run is already {run.status}")
    
    # Update run status to running
    run.status = RunStatus.RUNNING.value
    run.started_at = datetime.utcnow()
    db.commit()
    
    print(f"🏃 Executing run {run_id} for task {task_id}...")
    
    try:
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
        run.logs = result["logs"][:50000] if result["logs"] else None  # Limit log size
        run.error_message = result["error"]
        run.duration_seconds = result["duration_seconds"]
        
        db.commit()
        
        # Update task statistics
        _update_task_stats(db, task)
        
        print(f"✅ Run {run_id} completed: {'PASSED' if result['success'] else 'FAILED'}")
        
        return {
            "run_id": run_id,
            "task_id": task_id,
            "status": run.status,
            "success": result["success"],
            "reward": result.get("reward", 0),
            "tests_total": result["tests_total"],
            "tests_passed": result["tests_passed"],
            "tests_failed": result["tests_failed"],
            "duration_seconds": result["duration_seconds"],
            "error": result["error"],
        }
        
    except Exception as e:
        # Mark run as failed
        run.status = RunStatus.ERROR.value
        run.completed_at = datetime.utcnow()
        run.error_message = str(e)
        db.commit()
        
        _update_task_stats(db, task)
        
        print(f"❌ Run {run_id} failed with error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/execute-one")
def execute_one_run(
    task_id: int,
    openrouter_api_key: str = Query(..., description="OpenRouter API key"),
    timeout_seconds: int = Query(1200, description="Timeout in seconds"),
    db: Session = Depends(get_db),
):
    """
    Quick endpoint: Create a run and execute it immediately.
    
    Useful for testing - uploads a task, creates one run, executes it.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Start task if pending
    if task.status == TaskStatus.PENDING.value:
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.utcnow()
    
    # Create a new run
    existing_runs = db.query(Run).filter(Run.task_id == task_id).count()
    run = Run(
        task_id=task_id,
        run_number=existing_runs + 1,
        status=RunStatus.PENDING.value,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    
    task.total_runs = existing_runs + 1
    db.commit()
    
    # Execute the run (reuse the execute_run logic)
    return execute_run(task_id, run.id, openrouter_api_key, timeout_seconds, db)


# ============== Async Execution Endpoints (Stage 4) ==============

@app.post("/api/tasks/{task_id}/execute-async")
def execute_task_async(
    task_id: int,
    openrouter_api_key: str = Query(..., description="OpenRouter API key"),
    timeout_seconds: int = Query(1200, description="Timeout per run in seconds"),
    db: Session = Depends(get_db),
):
    """
    Execute ALL runs for a task asynchronously.
    
    This endpoint returns immediately. Runs are executed in the background
    by Celery workers. Poll /api/tasks/{task_id} to check progress.
    
    This is the main endpoint for Stage 4 / Goal 2.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Task is already {task.status}")
    
    # Update task status
    task.status = TaskStatus.RUNNING.value
    task.started_at = datetime.utcnow()
    
    # Create all runs
    run_ids = []
    for run_num in range(1, task.num_runs + 1):
        run = Run(
            task_id=task.id,
            run_number=run_num,
            status=RunStatus.PENDING.value,
        )
        db.add(run)
        db.flush()
        run_ids.append(run.id)
    
    task.total_runs = task.num_runs
    db.commit()
    
    print(f"🚀 Queuing {task.num_runs} async runs for task {task_id}")
    
    # Queue each run as a Celery task
    for run_id in run_ids:
        execute_harbor_run.delay(
            task_id=task_id,
            run_id=run_id,
            openrouter_api_key=openrouter_api_key,
            timeout_seconds=timeout_seconds,
        )
    
    return {
        "message": f"Task queued with {task.num_runs} runs",
        "task_id": task_id,
        "runs_queued": len(run_ids),
        "status": "running",
        "poll_url": f"/api/tasks/{task_id}",
    }


@app.post("/api/tasks/{task_id}/runs/{run_id}/execute-async")
def execute_run_async(
    task_id: int,
    run_id: int,
    openrouter_api_key: str = Query(..., description="OpenRouter API key"),
    timeout_seconds: int = Query(1200, description="Timeout in seconds"),
    db: Session = Depends(get_db),
):
    """
    Execute a single run asynchronously.
    
    Returns immediately. Poll /api/tasks/{task_id}/runs/{run_id} to check progress.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    run = db.query(Run).filter(Run.id == run_id, Run.task_id == task_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if run.status not in [RunStatus.PENDING.value]:
        raise HTTPException(status_code=400, detail=f"Run is already {run.status}")
    
    print(f"🚀 Queuing async run {run_id} for task {task_id}")
    
    # Queue the run
    execute_harbor_run.delay(
        task_id=task_id,
        run_id=run_id,
        openrouter_api_key=openrouter_api_key,
        timeout_seconds=timeout_seconds,
    )
    
    return {
        "message": "Run queued",
        "task_id": task_id,
        "run_id": run_id,
        "status": "queued",
        "poll_url": f"/api/tasks/{task_id}/runs/{run_id}",
    }


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


# ============== Run Endpoints ==============

@app.get("/api/tasks/{task_id}/runs", response_model=List[RunResponse])
async def list_runs(task_id: int, db: Session = Depends(get_db)):
    """List all runs for a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    runs = db.query(Run).filter(Run.task_id == task_id).order_by(Run.run_number).all()
    return runs


@app.get("/api/tasks/{task_id}/runs/{run_id}", response_model=RunResponse)
async def get_run(task_id: int, run_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific run."""
    run = db.query(Run).filter(Run.id == run_id, Run.task_id == task_id).first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return run


@app.get("/api/tasks/{task_id}/runs/{run_id}/logs")
async def get_run_logs(task_id: int, run_id: int, db: Session = Depends(get_db)):
    """Get full logs for a specific run."""
    run = db.query(Run).filter(Run.id == run_id, Run.task_id == task_id).first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return {
        "run_id": run_id,
        "task_id": task_id,
        "run_number": run.run_number,
        "status": run.status,
        "logs": run.logs or "",
        "error_message": run.error_message,
    }


# ============== Statistics ==============

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get overall statistics."""
    total_tasks = db.query(Task).count()
    pending_tasks = db.query(Task).filter(Task.status == TaskStatus.PENDING.value).count()
    running_tasks = db.query(Task).filter(Task.status == TaskStatus.RUNNING.value).count()
    completed_tasks = db.query(Task).filter(Task.status == TaskStatus.COMPLETED.value).count()
    failed_tasks = db.query(Task).filter(Task.status == TaskStatus.FAILED.value).count()
    
    total_runs = db.query(Run).count()
    passed_runs = db.query(Run).filter(Run.status == RunStatus.PASSED.value).count()
    failed_runs = db.query(Run).filter(Run.status == RunStatus.FAILED.value).count()
    
    return {
        "tasks": {
            "total": total_tasks,
            "pending": pending_tasks,
            "running": running_tasks,
            "completed": completed_tasks,
            "failed": failed_tasks,
        },
        "runs": {
            "total": total_runs,
            "passed": passed_runs,
            "failed": failed_runs,
        }
    }


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
