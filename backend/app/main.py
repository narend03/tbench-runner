"""FastAPI main application for TBench Runner."""

import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import structlog

from .config import get_settings, AVAILABLE_MODELS, AVAILABLE_AGENTS
from .database import get_db, create_tables
from .models import (
    Task, Run, TaskStatus, RunStatus,
    TaskCreate, TaskResponse, TaskDetailResponse, RunResponse,
    ModelsResponse, AgentsResponse
)
from .tasks import execute_task, execute_run

settings = get_settings()
logger = structlog.get_logger()

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
    
    logger.info("TBench Runner started")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "TBench Runner",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Models and Agents endpoints

@app.get("/api/models", response_model=List[ModelsResponse])
async def get_models():
    """Get available models for task execution."""
    return AVAILABLE_MODELS


@app.get("/api/agents", response_model=List[AgentsResponse])
async def get_agents():
    """Get available agents/harnesses for task execution."""
    return AVAILABLE_AGENTS


# Task endpoints

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(
    file: UploadFile = File(...),
    name: str = Query(..., description="Task name"),
    model: str = Query("openai/gpt-4o", description="Model to use"),
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
    # Validate file
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a zip archive")
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Seek back to start
    
    if file_size > settings.max_upload_size:
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Maximum size is {settings.max_upload_size // (1024*1024)}MB"
        )
    
    # Generate unique filename and save
    task_id = str(uuid.uuid4())
    upload_dir = Path(settings.upload_dir) / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
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
    
    logger.info(
        "Task created",
        task_id=task.id,
        name=name,
        model=model,
        agent=agent,
        num_runs=num_runs
    )
    
    # Start task execution asynchronously
    execute_task.delay(task.id)
    
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
    
    # Delete uploaded file
    try:
        file_path = Path(task.file_path)
        if file_path.exists():
            file_path.unlink()
        if file_path.parent.exists():
            shutil.rmtree(file_path.parent)
    except Exception as e:
        logger.warning("Failed to delete task files", error=str(e))
    
    # Delete task (cascades to runs)
    db.delete(task)
    db.commit()
    
    return {"message": "Task deleted successfully"}


@app.post("/api/tasks/{task_id}/retry")
async def retry_task(task_id: int, db: Session = Depends(get_db)):
    """Retry a failed task."""
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
    
    # Restart execution
    execute_task.delay(task.id)
    
    return {"message": "Task retry started"}


# Run endpoints

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
        "logs": run.logs or "",
        "error_message": run.error_message,
    }


# Statistics endpoint

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)

