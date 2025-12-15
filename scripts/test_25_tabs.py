#!/usr/bin/env python3
"""
Simulates 25 browser tabs each uploading a task with 10 runs.
Total: 250 runs with GPT-5.2 + terminus-2
"""

import asyncio
import aiohttp
import time
import os

API_BASE = "http://tbench-runner-alb-1936777750.us-west-2.elb.amazonaws.com"
ZIP_PATH = "sample-tasks/break-filter-js-from-html.zip"
NUM_TABS = 25
RUNS_PER_TAB = 10
# API Key - set via environment variable or replace with your key
API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_API_KEY_HERE")

async def upload_task(session, tab_num):
    """Simulate one browser tab uploading and starting a task."""
    try:
        # Upload task
        with open(ZIP_PATH, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=f'task_tab_{tab_num}.zip')
            
            url = f"{API_BASE}/api/tasks?name=test-tab-{tab_num}&model=openrouter/openai/gpt-5.2&agent=terminus-2&num_runs={RUNS_PER_TAB}"
            
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    print(f"❌ Tab {tab_num}: Upload failed - {await resp.text()}")
                    return None
                task = await resp.json()
                task_id = task['id']
                print(f"📤 Tab {tab_num}: Uploaded task {task_id}")
        
        # Start execution
        async with session.post(
            f"{API_BASE}/api/tasks/{task_id}/execute-async",
            params={"openrouter_api_key": API_KEY}
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"▶️  Tab {tab_num}: Started {result['runs_queued']} runs for task {task_id}")
                return task_id
            else:
                print(f"❌ Tab {tab_num}: Start failed - {await resp.text()}")
                return None
                
    except Exception as e:
        print(f"❌ Tab {tab_num}: Error - {e}")
        return None

async def check_progress(session, task_ids):
    """Check progress of all tasks."""
    total_runs = len(task_ids) * RUNS_PER_TAB
    
    while True:
        completed = 0
        passed = 0
        failed = 0
        running = 0
        
        for task_id in task_ids:
            try:
                async with session.get(f"{API_BASE}/api/tasks/{task_id}") as resp:
                    if resp.status == 200:
                        task = await resp.json()
                        passed += task.get('passed_runs', 0)
                        failed += task.get('failed_runs', 0)
                        
                        # Count running
                        for run in task.get('runs', []):
                            if run['status'] == 'running':
                                running += 1
            except:
                pass
        
        completed = passed + failed
        pct = (completed / total_runs) * 100 if total_runs > 0 else 0
        
        print(f"\r⏳ Progress: {completed}/{total_runs} ({pct:.1f}%) | ✅ {passed} | ❌ {failed} | 🏃 {running} running    ", end="", flush=True)
        
        if completed >= total_runs:
            print()
            return passed, failed
        
        await asyncio.sleep(5)

async def main():
    print(f"🚀 Simulating {NUM_TABS} browser tabs, each with {RUNS_PER_TAB} runs")
    print(f"📊 Total runs: {NUM_TABS * RUNS_PER_TAB}")
    print(f"🤖 Model: GPT-5.2 | Agent: terminus-2")
    print()
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Upload all tasks simultaneously (like 25 tabs)
        print("=" * 50)
        print("Phase 1: Uploading tasks (simulating 25 tabs)...")
        print("=" * 50)
        
        tasks = [upload_task(session, i+1) for i in range(NUM_TABS)]
        task_ids = await asyncio.gather(*tasks)
        task_ids = [t for t in task_ids if t is not None]
        
        upload_time = time.time() - start_time
        print()
        print(f"✅ Uploaded {len(task_ids)}/{NUM_TABS} tasks in {upload_time:.1f}s")
        print()
        
        if not task_ids:
            print("❌ No tasks created!")
            return
        
        # Monitor progress
        print("=" * 50)
        print("Phase 2: Monitoring execution...")
        print("=" * 50)
        
        passed, failed = await check_progress(session, task_ids)
        
        total_time = time.time() - start_time
        
        print()
        print("=" * 50)
        print("RESULTS")
        print("=" * 50)
        print(f"Tasks created:   {len(task_ids)}/{NUM_TABS}")
        print(f"Total runs:      {passed + failed}/{NUM_TABS * RUNS_PER_TAB}")
        print(f"Passed:          {passed} ({passed/(passed+failed)*100:.1f}%)" if passed+failed > 0 else "Passed: 0")
        print(f"Failed:          {failed}")
        print(f"Total time:      {total_time/60:.1f} minutes")
        print(f"Throughput:      {(passed+failed)/(total_time/60):.1f} runs/minute")

if __name__ == "__main__":
    asyncio.run(main())
