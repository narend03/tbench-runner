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

from .config import get_settings

settings = get_settings()


class HarborRunner:
    """Runs Terminal-Bench tasks using the Harbor framework."""
    
    def __init__(
        self,
        task_path: str,
        model: str,
        agent: str = "terminus-2",
        jobs_dir: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
    ):
        self.task_path = Path(task_path)
        self.model = model
        self.agent = agent
        self.jobs_dir = Path(jobs_dir) if jobs_dir else Path(settings.jobs_dir)
        self.openrouter_api_key = openrouter_api_key
        
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
        
        print(f"📦 Extracted task to: {task_dir}")
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
        timeout_seconds: int = 1200,  # 20 minutes default
    ) -> Dict[str, Any]:
        """
        Run a single attempt of the task.
        
        Returns dict with:
            - success: bool
            - reward: float (0.0 or 1.0)
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
        cmd = self._build_harbor_command(run_jobs_dir)
        
        print(f"🚀 Starting Harbor run: {run_id}")
        print(f"   Task: {self.task_path}")
        print(f"   Model: {self.model}")
        print(f"   Agent: {self.agent}")
        print(f"   Command: {' '.join(cmd)}")
        
        try:
            # Set up environment with API keys
            # Using OpenRouter for LLM access
            env = os.environ.copy()
            
            if self.openrouter_api_key:
                # OpenRouter uses OPENAI_API_KEY but with their base URL
                env["OPENAI_API_KEY"] = self.openrouter_api_key
                env["OPENROUTER_API_KEY"] = self.openrouter_api_key
            
            # Set OpenRouter base URL for litellm
            env["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
            
            # Add harbor to PATH
            home = os.path.expanduser("~")
            env["PATH"] = f"{home}/.local/bin:" + env.get("PATH", "")
            
            # Run harbor command
            print(f"⏳ Running Harbor (timeout: {timeout_seconds}s)...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            
            logs = result.stdout + "\n" + result.stderr
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            print(f"✅ Harbor finished in {duration:.1f}s (exit code: {result.returncode})")
            
            # Parse results from Harbor output directory
            reward, tests_total, tests_passed, tests_failed, test_logs = self._parse_harbor_output(run_jobs_dir)
            
            # Combine logs
            full_logs = logs
            if test_logs:
                full_logs += "\n\n=== TEST OUTPUT ===\n" + test_logs
            
            return {
                "success": reward > 0,
                "reward": reward,
                "tests_total": tests_total,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "logs": full_logs,
                "error": None if result.returncode == 0 else f"Exit code: {result.returncode}",
                "duration_seconds": duration,
                "output_path": str(run_jobs_dir),
            }
                
        except subprocess.TimeoutExpired:
            duration = (datetime.utcnow() - start_time).total_seconds()
            print(f"⏰ Harbor timed out after {duration:.1f}s")
            return {
                "success": False,
                "reward": 0.0,
                "tests_total": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "logs": f"Task timed out after {timeout_seconds} seconds",
                "error": "Timeout",
                "duration_seconds": duration,
                "output_path": str(run_jobs_dir),
            }
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            print(f"❌ Harbor failed: {e}")
            return {
                "success": False,
                "reward": 0.0,
                "tests_total": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "logs": str(e),
                "error": str(e),
                "duration_seconds": duration,
                "output_path": str(run_jobs_dir),
            }
    
    def _build_harbor_command(self, output_dir: Path) -> list:
        """Build the harbor CLI command."""
        cmd = [
            "harbor", "run",
            "--path", str(self.task_path),
            "--agent", self.agent,
            "--jobs-dir", str(output_dir),
            "--n-attempts", "1",
            "--n-concurrent", "1",
        ]
        
        # Add model if specified (not for oracle agent)
        if self.agent != "oracle" and self.model:
            cmd.extend(["--model", self.model])
        
        return cmd
    
    def _parse_harbor_output(self, output_dir: Path) -> Tuple[float, int, int, int, str]:
        """
        Parse Harbor output directory for results.
        
        Returns: (reward, tests_total, tests_passed, tests_failed, test_logs)
        """
        reward = 0.0
        tests_total = 0
        tests_passed = 0
        tests_failed = 0
        test_logs = ""
        
        # Find the trial directory (format: taskname__randomid)
        trial_dirs = list(output_dir.rglob("*__*"))
        if not trial_dirs:
            # Try finding any subdirectory with verifier folder
            trial_dirs = [d for d in output_dir.iterdir() if d.is_dir() and (d / "verifier").exists()]
        
        for trial_dir in trial_dirs:
            if not trial_dir.is_dir():
                continue
                
            # Parse reward.txt
            reward_file = trial_dir / "verifier" / "reward.txt"
            if reward_file.exists():
                try:
                    reward = float(reward_file.read_text().strip())
                    print(f"   Reward: {reward}")
                except (ValueError, IOError):
                    pass
            
            # Parse ctrf.json for detailed test results
            ctrf_file = trial_dir / "verifier" / "ctrf.json"
            if ctrf_file.exists():
                try:
                    with open(ctrf_file) as f:
                        ctrf_data = json.load(f)
                    
                    summary = ctrf_data.get("results", {}).get("summary", {})
                    tests_total = summary.get("tests", 0)
                    tests_passed = summary.get("passed", 0)
                    tests_failed = summary.get("failed", 0)
                    print(f"   Tests: {tests_passed}/{tests_total} passed")
                except (json.JSONDecodeError, IOError):
                    pass
            
            # Read test output
            test_stdout = trial_dir / "verifier" / "test-stdout.txt"
            if test_stdout.exists():
                try:
                    test_logs = test_stdout.read_text()[-5000:]  # Last 5KB
                except IOError:
                    pass
            
            # If we found results, break (use first trial)
            if reward > 0 or tests_total > 0:
                break
        
        # Fallback: determine pass/fail from reward
        if tests_total == 0 and reward > 0:
            tests_total = 1
            tests_passed = 1
        elif tests_total == 0 and reward == 0:
            # Check if there was actually a run
            if trial_dirs:
                tests_total = 1
                tests_failed = 1
        
        return reward, tests_total, tests_passed, tests_failed, test_logs


def run_task_sync(
    zip_path: str,
    model: str,
    agent: str = "terminus-2",
    openrouter_api_key: Optional[str] = None,
    run_id: Optional[str] = None,
    timeout_seconds: int = 1200,
) -> Dict[str, Any]:
    """
    Run a Terminal-Bench task synchronously.
    
    This extracts the zip, runs Harbor, and returns the results.
    """
    if run_id is None:
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    # Create temp directory for extraction
    temp_dir = tempfile.mkdtemp(prefix="tbench_")
    
    try:
        # Initialize runner
        runner = HarborRunner(
            task_path=temp_dir,
            model=model,
            agent=agent,
            openrouter_api_key=openrouter_api_key,
        )
        
        # Extract task
        task_dir = runner.extract_task(zip_path, temp_dir)
        runner.task_path = Path(task_dir)
        
        # Run task
        result = runner.run_single(run_id, timeout_seconds=timeout_seconds)
        
        return result
        
    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
