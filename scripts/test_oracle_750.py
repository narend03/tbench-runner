#!/usr/bin/env python3
"""
Run 750 oracle agent runs (15 users × 5 tasks × 10 runs)
This tests infrastructure without LLM costs.
"""

import asyncio
import aiohttp
import time

API_BASE = "http://tbench-runner-alb-1936777750.us-west-2.elb.amazonaws.com"
ZIP_PATH = "sample-tasks/break-filter-js-from-html.zip"
NUM_USERS = 15
TASKS_PER_USER = 5
RUNS_PER_TASK = 10
TOTAL_RUNS = NUM_USERS * TASKS_PER_USER * RUNS_PER_TASK
API_KEY = "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"

async def upload_and_start_task(session, user_num, task_num):
    """Upload a task and start execution with oracle agent."""
    try:
        # Upload task
        with open(ZIP_PATH, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=f'oracle-test-user{user_num}-task{task_num}.zip')
            
            url = f"{API_BASE}/api/tasks?name=oracle-user{user_num}-task{task_num}&model=openrouter/openai/gpt-4o&agent=oracle&num_runs={RUNS_PER_TASK}"
            
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"❌ User {user_num}, Task {task_num}: Upload failed - {text}")
                    return None
                task = await resp.json()
                task_id = task['id']
        
        # Start execution (oracle doesn't need API key, but we'll pass it anyway)
        async with session.post(
            f"{API_BASE}/api/tasks/{task_id}/execute-async",
            params={"openrouter_api_key": API_KEY}
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print(f"✅ User {user_num}, Task {task_num}: Task {task_id} - {result['runs_queued']} runs queued")
                return task_id
            else:
                text = await resp.text()
                print(f"❌ User {user_num}, Task {task_num}: Start failed - {text}")
                return None
                
    except Exception as e:
        print(f"❌ User {user_num}, Task {task_num}: Error - {e}")
        return None

async def check_progress(session, task_ids):
    """Check progress of all tasks."""
    total_runs = len(task_ids) * RUNS_PER_TASK
    
    while True:
        completed = 0
        passed = 0
        failed = 0
        running = 0
        pending = 0
        
        for task_id in task_ids:
            try:
                async with session.get(f"{API_BASE}/api/tasks/{task_id}") as resp:
                    if resp.status == 200:
                        task = await resp.json()
                        passed += task.get('passed_runs', 0)
                        failed += task.get('failed_runs', 0)
                        
                        # Count running/pending
                        for run in task.get('runs', []):
                            if run['status'] == 'running':
                                running += 1
                            elif run['status'] == 'pending':
                                pending += 1
            except Exception as e:
                pass
        
        completed = passed + failed
        pct = (completed / total_runs) * 100 if total_runs > 0 else 0
        
        print(f"\r⏳ Progress: {completed}/{total_runs} ({pct:.1f}%) | ✅ {passed} | ❌ {failed} | 🏃 {running} running | ⏸️  {pending} pending    ", end="", flush=True)
        
        if completed >= total_runs:
            print()
            return passed, failed
        
        await asyncio.sleep(5)

async def main():
    print("=" * 70)
    print("ORACLE AGENT TEST: 750 Runs")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  • Users: {NUM_USERS}")
    print(f"  • Tasks per user: {TASKS_PER_USER}")
    print(f"  • Runs per task: {RUNS_PER_TASK}")
    print(f"  • Total runs: {TOTAL_RUNS}")
    print(f"  • Agent: oracle (FREE - no LLM costs)")
    print()
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Upload all tasks simultaneously
        print("=" * 70)
        print("Phase 1: Uploading tasks...")
        print("=" * 70)
        
        tasks = []
        for user_num in range(1, NUM_USERS + 1):
            for task_num in range(1, TASKS_PER_USER + 1):
                tasks.append(upload_and_start_task(session, user_num, task_num))
        
        task_ids = await asyncio.gather(*tasks)
        task_ids = [t for t in task_ids if t is not None]
        
        upload_time = time.time() - start_time
        print()
        print(f"✅ Uploaded {len(task_ids)}/{NUM_USERS * TASKS_PER_USER} tasks in {upload_time:.1f}s")
        print()
        
        if not task_ids:
            print("❌ No tasks created!")
            return
        
        # Monitor progress
        print("=" * 70)
        print("Phase 2: Monitoring execution...")
        print("=" * 70)
        print("(Oracle agent runs are fast - ~30 seconds each)")
        print()
        
        passed, failed = await check_progress(session, task_ids)
        
        total_time = time.time() - start_time
        
        print()
        print("=" * 70)
        print("RESULTS")
        print("=" * 70)
        print(f"Tasks created:   {len(task_ids)}/{NUM_USERS * TASKS_PER_USER}")
        print(f"Total runs:      {passed + failed}/{TOTAL_RUNS}")
        print(f"Passed:          {passed} ({passed/(passed+failed)*100:.1f}%)" if passed+failed > 0 else "Passed: 0")
        print(f"Failed:          {failed}")
        print(f"Total time:      {total_time/60:.1f} minutes")
        print(f"Throughput:      {(passed+failed)/(total_time/60):.1f} runs/minute")
        print()
        print("💰 Cost: ~$0.10 (infrastructure only, no LLM costs)")
        print("✅ Oracle agent is FREE for LLM calls!")

if __name__ == "__main__":
    asyncio.run(main())
