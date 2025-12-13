#!/usr/bin/env python3
"""
Load Test Script for TBench Runner
Tests concurrent task execution to verify Goal 3 (600 concurrent runs)
"""

import asyncio
import aiohttp
import time
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List
import json

@dataclass
class TestResult:
    task_id: int
    status: str
    passed: int
    total: int
    duration: float
    error: str = None

class LoadTester:
    def __init__(self, base_url: str, api_key: str, task_zip_path: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.task_zip_path = Path(task_zip_path)
        self.results: List[TestResult] = []
        
    async def upload_and_execute_task(self, session: aiohttp.ClientSession, task_num: int, num_runs: int) -> TestResult:
        """Upload a task and execute it."""
        start_time = time.time()
        
        try:
            # Upload task
            with open(self.task_zip_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=self.task_zip_path.name)
                
                async with session.post(
                    f"{self.base_url}/api/tasks",
                    params={
                        'name': f'LoadTest-{task_num}',
                        'model': 'openai/gpt-5.2',
                        'agent': 'oracle',  # Use oracle for fast execution
                        'num_runs': num_runs
                    },
                    data=data
                ) as resp:
                    if resp.status != 200:
                        return TestResult(0, 'upload_failed', 0, 0, time.time() - start_time, await resp.text())
                    task_data = await resp.json()
                    task_id = task_data['id']
            
            # Execute task
            async with session.post(
                f"{self.base_url}/api/tasks/{task_id}/execute-async",
                params={'openrouter_api_key': self.api_key}
            ) as resp:
                if resp.status != 200:
                    return TestResult(task_id, 'execute_failed', 0, 0, time.time() - start_time, await resp.text())
            
            # Poll for completion (max 10 minutes)
            for _ in range(120):  # 120 × 5s = 10 minutes
                await asyncio.sleep(5)
                async with session.get(f"{self.base_url}/api/tasks/{task_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data['status'] == 'completed':
                            return TestResult(
                                task_id, 
                                'completed',
                                data['passed_runs'],
                                data['total_runs'],
                                time.time() - start_time
                            )
            
            return TestResult(task_id, 'timeout', 0, 0, time.time() - start_time)
            
        except Exception as e:
            return TestResult(0, 'error', 0, 0, time.time() - start_time, str(e))
    
    async def run_load_test(self, num_tasks: int, runs_per_task: int, concurrency: int):
        """Run the load test with specified parameters."""
        print(f"\n{'='*60}")
        print(f"LOAD TEST: {num_tasks} tasks × {runs_per_task} runs = {num_tasks * runs_per_task} total runs")
        print(f"Concurrency: {concurrency} simultaneous uploads")
        print(f"{'='*60}\n")
        
        connector = aiohttp.TCPConnector(limit=concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Create semaphore for controlled concurrency
            sem = asyncio.Semaphore(concurrency)
            
            async def bounded_task(task_num):
                async with sem:
                    print(f"  Starting task {task_num}...")
                    result = await self.upload_and_execute_task(session, task_num, runs_per_task)
                    self.results.append(result)
                    status_icon = "✅" if result.status == 'completed' and result.passed == result.total else "❌"
                    print(f"  {status_icon} Task {task_num}: {result.status} ({result.passed}/{result.total}) in {result.duration:.1f}s")
                    return result
            
            start_time = time.time()
            tasks = [bounded_task(i) for i in range(1, num_tasks + 1)]
            await asyncio.gather(*tasks)
            total_time = time.time() - start_time
        
        # Print summary
        self.print_summary(num_tasks, runs_per_task, total_time)
    
    def print_summary(self, num_tasks: int, runs_per_task: int, total_time: float):
        completed = [r for r in self.results if r.status == 'completed']
        passed = [r for r in completed if r.passed == r.total]
        failed = [r for r in self.results if r.status != 'completed']
        
        total_runs = num_tasks * runs_per_task
        actual_runs = sum(r.total for r in completed)
        passed_runs = sum(r.passed for r in completed)
        
        print(f"\n{'='*60}")
        print("LOAD TEST RESULTS")
        print(f"{'='*60}")
        print(f"Tasks:           {len(completed)}/{num_tasks} completed")
        print(f"Runs:            {passed_runs}/{actual_runs} passed")
        print(f"Total Time:      {total_time:.1f}s")
        print(f"Throughput:      {actual_runs / total_time:.2f} runs/second")
        print(f"Avg Task Time:   {sum(r.duration for r in completed) / len(completed):.1f}s" if completed else "N/A")
        print(f"{'='*60}")
        
        if failed:
            print(f"\nFailed Tasks ({len(failed)}):")
            for r in failed[:5]:
                print(f"  Task {r.task_id}: {r.status} - {r.error[:100] if r.error else 'unknown'}")
        
        # Output JSON summary
        summary = {
            'total_tasks': num_tasks,
            'completed_tasks': len(completed),
            'total_runs_requested': total_runs,
            'total_runs_executed': actual_runs,
            'passed_runs': passed_runs,
            'total_time_seconds': total_time,
            'throughput_runs_per_second': actual_runs / total_time if total_time > 0 else 0
        }
        print(f"\nJSON Summary: {json.dumps(summary)}")

async def main():
    parser = argparse.ArgumentParser(description='Load test TBench Runner')
    parser.add_argument('--url', default='http://tbench-runner-alb-1936777750.us-west-2.elb.amazonaws.com',
                        help='Base URL of the TBench Runner API')
    parser.add_argument('--api-key', required=True, help='OpenRouter API key')
    parser.add_argument('--task-zip', required=True, help='Path to task ZIP file')
    parser.add_argument('--tasks', type=int, default=10, help='Number of tasks to create')
    parser.add_argument('--runs', type=int, default=1, help='Runs per task')
    parser.add_argument('--concurrency', type=int, default=5, help='Concurrent uploads')
    
    args = parser.parse_args()
    
    tester = LoadTester(args.url, args.api_key, args.task_zip)
    await tester.run_load_test(args.tasks, args.runs, args.concurrency)

if __name__ == '__main__':
    asyncio.run(main())

