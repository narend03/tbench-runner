"""Database models for TBench Runner."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel


Base = declarative_base()


class TaskStatus(str, Enum):
    """Status of a task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    """Status of an individual run."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


# SQLAlchemy Models

class Task(Base):
    """A Terminal-Bench task uploaded by a user."""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # File info
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    
    # Configuration
    model = Column(String(100), nullable=False)
    agent = Column(String(50), nullable=False, default="terminus-2")
    harness = Column(String(50), nullable=False, default="harbor")
    num_runs = Column(Integer, nullable=False, default=10)
    
    # Status
    status = Column(String(20), nullable=False, default=TaskStatus.PENDING.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # User tracking
    user_session_id = Column(String(100), nullable=True)
    
    # Results summary
    total_runs = Column(Integer, default=0)
    passed_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)
    
    # Relationships
    runs = relationship("Run", back_populates="task", cascade="all, delete-orphan")


class Run(Base):
    """An individual run of a task."""
    __tablename__ = "runs"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    run_number = Column(Integer, nullable=False)
    
    # Status
    status = Column(String(20), nullable=False, default=RunStatus.PENDING.value)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Results
    tests_total = Column(Integer, default=0)
    tests_passed = Column(Integer, default=0)
    tests_failed = Column(Integer, default=0)
    
    # Logs and output
    logs = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    output_path = Column(String(512), nullable=True)
    
    # Metrics
    duration_seconds = Column(Float, nullable=True)
    
    # Episode/trajectory data
    episode_data = Column(JSON, nullable=True)
    
    # Relationship
    task = relationship("Task", back_populates="runs")


# Pydantic Schemas

class TaskCreate(BaseModel):
    """Schema for creating a new task."""
    name: str
    model: str = "openai/gpt-4o"
    agent: str = "terminus-2"
    harness: str = "harbor"
    num_runs: int = 10


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: int
    name: str
    description: Optional[str]
    original_filename: str
    model: str
    agent: str
    harness: str
    num_runs: int
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    total_runs: int
    passed_runs: int
    failed_runs: int
    
    class Config:
        from_attributes = True


class RunResponse(BaseModel):
    """Schema for run response."""
    id: int
    task_id: int
    run_number: int
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    tests_total: int
    tests_passed: int
    tests_failed: int
    logs: Optional[str]
    error_message: Optional[str]
    duration_seconds: Optional[float]
    
    class Config:
        from_attributes = True


class TaskDetailResponse(BaseModel):
    """Schema for detailed task response with runs."""
    id: int
    name: str
    description: Optional[str]
    original_filename: str
    model: str
    agent: str
    harness: str
    num_runs: int
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    total_runs: int
    passed_runs: int
    failed_runs: int
    runs: List[RunResponse]
    
    class Config:
        from_attributes = True


class ModelsResponse(BaseModel):
    """Schema for available models response."""
    id: str
    name: str
    provider: str


class AgentsResponse(BaseModel):
    """Schema for available agents response."""
    id: str
    name: str
    harness: str

