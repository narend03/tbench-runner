"""File storage abstraction - supports local and S3."""

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional
import uuid

from .config import get_settings

settings = get_settings()

# Lazy import boto3 only when needed
_s3_client = None


def get_s3_client():
    """Get or create S3 client."""
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
    return _s3_client


def save_upload(file: BinaryIO, filename: str, task_id: str = None) -> str:
    """
    Save an uploaded file.
    
    Returns the path/key where the file is stored.
    """
    if task_id is None:
        task_id = str(uuid.uuid4())
    
    if settings.use_s3:
        return _save_to_s3(file, filename, task_id)
    else:
        return _save_to_local(file, filename, task_id)


def _save_to_local(file: BinaryIO, filename: str, task_id: str) -> str:
    """Save file to local filesystem."""
    upload_dir = Path(settings.upload_dir) / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / filename
    
    with open(file_path, 'wb') as f:
        shutil.copyfileobj(file, f)
    
    return str(file_path)


def _save_to_s3(file: BinaryIO, filename: str, task_id: str) -> str:
    """Save file to S3."""
    s3 = get_s3_client()
    key = f"uploads/{task_id}/{filename}"
    
    s3.upload_fileobj(file, settings.s3_bucket_name, key)
    
    return f"s3://{settings.s3_bucket_name}/{key}"


def get_file(path: str) -> Optional[str]:
    """
    Get a file and return local path.
    
    For S3, downloads to temp location first.
    """
    if path.startswith("s3://"):
        return _download_from_s3(path)
    else:
        if os.path.exists(path):
            return path
        return None


def _download_from_s3(s3_path: str) -> str:
    """Download file from S3 to temp location."""
    import tempfile
    
    s3 = get_s3_client()
    
    # Parse s3://bucket/key format
    parts = s3_path.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1]
    
    # Create temp file
    suffix = os.path.splitext(key)[1]
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    
    s3.download_file(bucket, key, temp_file.name)
    
    return temp_file.name


def delete_file(path: str) -> bool:
    """Delete a file."""
    try:
        if path.startswith("s3://"):
            return _delete_from_s3(path)
        else:
            if os.path.exists(path):
                os.remove(path)
                # Try to remove parent directory if empty
                parent = os.path.dirname(path)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
            return True
    except Exception as e:
        print(f"Failed to delete file {path}: {e}")
        return False


def _delete_from_s3(s3_path: str) -> bool:
    """Delete file from S3."""
    try:
        s3 = get_s3_client()
        
        # Parse s3://bucket/key format
        parts = s3_path.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1]
        
        s3.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception as e:
        print(f"Failed to delete from S3 {s3_path}: {e}")
        return False

