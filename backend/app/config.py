"""Configuration settings for the TBench Runner backend."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "TBench Runner"
    environment: str = "development"  # development, staging, production
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database - PostgreSQL for production, SQLite for dev
    database_url: str = "sqlite:///./tbench_runner.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # File storage - local for dev, S3 for production
    storage_backend: str = "local"  # "local" or "s3"
    upload_dir: str = "./uploads"
    jobs_dir: str = "./jobs"
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    
    # AWS S3 (for production)
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket_name: str = ""
    
    # Harbor settings
    harbor_timeout_multiplier: float = 1.0
    harbor_default_agent: str = "terminus-2"
    harbor_default_env: str = "docker"
    harbor_n_concurrent: int = 4
    
    # OpenRouter API (required for LLM execution)
    openrouter_api_key: str = ""
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    
    # Default model
    default_model: str = "openai/gpt-5.2"
    
    # Task limits
    max_runs_per_task: int = 10
    max_concurrent_runs: int = 600  # 15 users x 5 tasks x 10 runs
    
    # CORS - update for production
    cors_origins: str = "*"
    
    # Frontend URL
    frontend_url: str = "http://localhost:3000"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def use_s3(self) -> bool:
        return self.storage_backend == "s3" and self.s3_bucket_name


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Available models for selection (via OpenRouter)
AVAILABLE_MODELS = [
    {"id": "openai/gpt-5.2", "name": "GPT-5.2 (Recommended)", "provider": "OpenAI"},
    {"id": "openai/gpt-5", "name": "GPT-5", "provider": "OpenAI"},
    {"id": "openai/gpt-5-mini", "name": "GPT-5 Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "provider": "Anthropic"},
]

# Available agents/harnesses
AVAILABLE_AGENTS = [
    {"id": "terminus-2", "name": "Terminus 2 (Harbor)", "harness": "harbor"},
    {"id": "terminus-1", "name": "Terminus 1 (Legacy)", "harness": "terminus"},
    {"id": "claude-code", "name": "Claude Code", "harness": "harbor"},
    {"id": "oracle", "name": "Oracle (Testing)", "harness": "harbor"},
]
