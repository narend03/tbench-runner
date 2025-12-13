"""Harbor task runner - executes Terminal-Bench tasks using Harbor framework."""

import os
import subprocess
import json
import tempfile
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import structlog

from .config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class HarborRunner:
    """Runs Terminal-Bench tasks using the Harbor framework."""
    
    def __init__(
        self,
        task_path: str,
        model: str,
        agent: str = "terminus-2",
        harness: str = "harbor",
        jobs_dir: Optional[str] = None,
    ):
        self.task_path = Path(task_path)
        self.model = model
        self.agent = agent
        self.harness = harness
        self.jobs_dir = Path(jobs_dir) if jobs_dir else Path(settings.jobs_dir)
        
        # Ensure jobs directory exists
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_task(self, zip_path: str, extract_to: str) -> str:
        """Extract a zipped task to a directory."""
        extract_path = Path(extract_to)
        extract_path.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Find the actual task directory (might be nested)
        task_dir = self._find_task_dir(extract_path)
        
        logger.info("Extracted task", zip_path=zip_path, task_dir=str(task_dir))
        return str(task_dir)
    
    def _find_task_dir(self, extract_path: Path) -> Path:
        """Find the actual task directory containing task.toml."""
        # Check if task.toml exists at root
        if (extract_path / "task.toml").exists():
            return extract_path
        
        # Check one level deep
        for subdir in extract_path.iterdir():
            if subdir.is_dir():
                if (subdir / "task.toml").exists():
                    return subdir
                # Check another level (in case of nested extraction)
                for subsubdir in subdir.iterdir():
                    if subsubdir.is_dir() and (subsubdir / "task.toml").exists():
                        return subsubdir
        
        # If no task.toml found, return the first directory
        for subdir in extract_path.iterdir():
            if subdir.is_dir():
                return subdir
        
        return extract_path
    
    def run_single(
        self,
        run_id: str,
        timeout_multiplier: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Run a single attempt of the task.
        
        Returns dict with:
            - success: bool
            - tests_total: int
            - tests_passed: int
            - tests_failed: int
            - logs: str
            - error: Optional[str]
            - duration_seconds: float
            - output_path: str
        """
        start_time = datetime.utcnow()
        run_jobs_dir = self.jobs_dir / run_id
        run_jobs_dir.mkdir(parents=True, exist_ok=True)
        
        # Build harbor command
        cmd = self._build_harbor_command(run_jobs_dir, timeout_multiplier)
        
        logger.info(
            "Starting harbor run",
            run_id=run_id,
            task_path=str(self.task_path),
            model=self.model,
            agent=self.agent,
            command=" ".join(cmd)
        )
        
        try:
            # Set up environment with API keys
            env = os.environ.copy()
            if settings.openrouter_api_key:
                env["OPENROUTER_API_KEY"] = settings.openrouter_api_key
                env["OPENAI_API_KEY"] = settings.openrouter_api_key
                env["OPENAI_API_BASE"] = settings.openrouter_base_url
            
            # Run harbor command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600 * timeout_multiplier,  # 1 hour default
                cwd=str(self.task_path.parent),
                env=env,
            )
            
            logs = result.stdout + "\n" + result.stderr
            
            # Parse results from output
            tests_total, tests_passed, tests_failed = self._parse_test_results(
                run_jobs_dir, logs
            )
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "tests_total": tests_total,
                    "tests_passed": tests_passed,
                    "tests_failed": tests_failed,
                    "logs": logs,
                    "error": None,
                    "duration_seconds": duration,
                    "output_path": str(run_jobs_dir),
                }
            else:
                return {
                    "success": False,
                    "tests_total": tests_total,
                    "tests_passed": tests_passed,
                    "tests_failed": tests_failed,
                    "logs": logs,
                    "error": f"Command failed with return code {result.returncode}",
                    "duration_seconds": duration,
                    "output_path": str(run_jobs_dir),
                }
                
        except subprocess.TimeoutExpired as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return {
                "success": False,
                "tests_total": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "logs": str(e),
                "error": "Task timed out",
                "duration_seconds": duration,
                "output_path": str(run_jobs_dir),
            }
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error("Harbor run failed", run_id=run_id, error=str(e))
            return {
                "success": False,
                "tests_total": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "logs": "",
                "error": str(e),
                "duration_seconds": duration,
                "output_path": str(run_jobs_dir),
            }
    
    def _build_harbor_command(
        self,
        output_dir: Path,
        timeout_multiplier: float
    ) -> list:
        """Build the harbor CLI command."""
        cmd = [
            "harbor", "run",
            "--path", str(self.task_path),
            "--agent", self.agent,
            "--jobs-dir", str(output_dir),
            "--n-attempts", "1",
            "--n-concurrent", "1",
            "--timeout-multiplier", str(timeout_multiplier),
        ]
        
        # Add model if specified (not for oracle agent)
        if self.agent != "oracle" and self.model:
            cmd.extend(["--model", self.model])
        
        return cmd
    
    def _parse_test_results(
        self,
        output_dir: Path,
        logs: str
    ) -> Tuple[int, int, int]:
        """Parse test results from Harbor output."""
        tests_total = 0
        tests_passed = 0
        tests_failed = 0
        
        # Try to find results.json or similar output
        for results_file in output_dir.rglob("*.json"):
            try:
                with open(results_file) as f:
                    data = json.load(f)
                    
                # Look for test results in various formats
                if "tests" in data:
                    tests = data["tests"]
                    tests_total = len(tests)
                    tests_passed = sum(1 for t in tests if t.get("passed", False))
                    tests_failed = tests_total - tests_passed
                elif "passed" in data:
                    tests_passed = int(data.get("passed", 0))
                    tests_failed = int(data.get("failed", 0))
                    tests_total = tests_passed + tests_failed
                elif "score" in data:
                    # Some formats use score as pass rate
                    score = float(data.get("score", 0))
                    tests_total = 1
                    tests_passed = 1 if score > 0.5 else 0
                    tests_failed = 1 - tests_passed
                    
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        
        # Fallback: parse from logs
        if tests_total == 0:
            tests_total, tests_passed, tests_failed = self._parse_logs_for_results(logs)
        
        return tests_total, tests_passed, tests_failed
    
    def _parse_logs_for_results(self, logs: str) -> Tuple[int, int, int]:
        """Parse test results from log output."""
        import re
        
        # Try pytest-style output: "X passed, Y failed"
        pytest_match = re.search(r'(\d+)\s+passed.*?(\d+)\s+failed', logs, re.IGNORECASE)
        if pytest_match:
            passed = int(pytest_match.group(1))
            failed = int(pytest_match.group(2))
            return passed + failed, passed, failed
        
        # Try simple passed/failed counts
        passed_match = re.search(r'(\d+)\s+(?:test|tests)\s+passed', logs, re.IGNORECASE)
        failed_match = re.search(r'(\d+)\s+(?:test|tests)\s+failed', logs, re.IGNORECASE)
        
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        
        if passed > 0 or failed > 0:
            return passed + failed, passed, failed
        
        # Check for success/failure indicators
        if "PASSED" in logs or "SUCCESS" in logs:
            return 1, 1, 0
        elif "FAILED" in logs or "ERROR" in logs:
            return 1, 0, 1
        
        return 0, 0, 0


def run_task_locally(
    task_zip_path: str,
    model: str,
    agent: str = "terminus-2",
    harness: str = "harbor",
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run a single Terminal-Bench task locally.
    
    This is a helper function for local testing (Goal 1).
    """
    if run_id is None:
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    # Create temp directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        runner = HarborRunner(
            task_path=temp_dir,
            model=model,
            agent=agent,
            harness=harness,
        )
        
        # Extract task
        task_dir = runner.extract_task(task_zip_path, temp_dir)
        runner.task_path = Path(task_dir)
        
        # Run task
        result = runner.run_single(run_id)
        
        return result

