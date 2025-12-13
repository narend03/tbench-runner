"""Configuration settings for the TBench Runner backend."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "TBench Runner"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database
    database_url: str = "sqlite:///./tbench_runner.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # File storage
    upload_dir: str = "./uploads"
    jobs_dir: str = "./jobs"
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    
    # Harbor settings
    harbor_timeout_multiplier: float = 1.0
    harbor_default_agent: str = "terminus-2"
    harbor_default_env: str = "docker"
    harbor_n_concurrent: int = 4
    
    # OpenRouter API
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # Supported models
    default_model: str = "openai/gpt-4o"
    
    # Task limits
    max_runs_per_task: int = 10
    max_concurrent_runs: int = 600  # 15 users x 5 tasks x 10 runs
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Available models for selection
AVAILABLE_MODELS = [
    {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "provider": "Anthropic"},
    {"id": "anthropic/claude-opus-4", "name": "Claude Opus 4", "provider": "Anthropic"},
    {"id": "google/gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash", "provider": "Google"},
]

# Available agents/harnesses
AVAILABLE_AGENTS = [
    {"id": "terminus-2", "name": "Terminus 2 (Harbor)", "harness": "harbor"},
    {"id": "terminus-1", "name": "Terminus 1 (Legacy)", "harness": "terminus"},
    {"id": "claude-code", "name": "Claude Code", "harness": "harbor"},
    {"id": "oracle", "name": "Oracle (Testing)", "harness": "harbor"},
]

