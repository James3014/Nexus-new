import sys
import os
import sys
import time
import json
import concurrent.futures
import subprocess
from pathlib import Path

# Ensure project imports work
sys.path.append(str(Path.cwd()))

from nexus.engine.coordinator import NexusEngine
from nexus.core.state_io import StateIO
from nexus.app.command_service import NexusCommandService


def execute_bug_task(service: NexusCommandService, task: dict) -> bool:
    return service.execute_bug(
        task["desc"],
        delivery_mode="standard",
        bug_id=task["id"],
    )

def run_task(project_root, task):
    print(f"🚀 [Parallel] Starting {task['id']}...")
    # Create isolated run directory
    run_dir = project_root / ".nexus" / "runs" / task['id']
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Isolated state file
    state_file = run_dir / "nexus_state.jsonl"
    state_io = StateIO(str(project_root), state_file=str(state_file))
    
    engine = NexusEngine(project_root, run_dir=run_dir, state_io=state_io)
    service = NexusCommandService(engine)
    
    start_time = time.time()
    try:
        success = execute_bug_task(service, task)
    except Exception as e:
        print(f"❌ [Parallel] {task['id']} Crashed: {e}")
        success = False
        
    duration = time.time() - start_time
    
    # Load final state for tokens
    final_state = state_io.load_global_state()
    tokens = final_state.phase_tokens if hasattr(final_state, "phase_tokens") else {}

    return {
        "id": task['id'],
        "type": task['type'],
        "success": success,
        "duration": duration,
        "tokens": tokens
    }

def run_v1_8_mega_benchmark():
    project_root = Path("/Users/jameschen/Downloads/Muse-Nexus")
    
    tasks = [
        {"type": "bug", "id": "BUG-301", "desc": "Fix recursion depth error in Jinja lexer"},
        {"type": "bug", "id": "BUG-302", "desc": "Fix Click argument parsing with multiple options"},
        {"type": "bug", "id": "BUG-303", "desc": "Fix race condition in session cleanup"},
        {"type": "bug", "id": "BUG-304", "desc": "Fix OAuth2 token refresh with expired client secret"},
        {"type": "bug", "id": "BUG-305", "desc": "Fix Django middleware CSRF bypass with custom headers"},
        {"type": "bug", "id": "BUG-306", "desc": "Fix N+1 query in bulk user update"},
        {"type": "bug", "id": "BUG-307", "desc": "Fix Redis lock timeout during heavy load"},
        {"type": "bug", "id": "BUG-308", "desc": "Fix memory leak in background thread pool"},
        {"type": "bug", "id": "BUG-309", "desc": "Fix incorrect type hint in StateIO loading"},
        {"type": "bug", "id": "BUG-310", "desc": "Fix malformed JSON output in Auditor reports"},
    ]
    
    print(f"🔥 Starting v1.8 Parallel Mega Benchmark (10 Bugs)...")
    
    # Pre-setup dummy files to avoid git lock issues in threads
    for t in tasks:
        dummy_file = project_root / f"src/bug_fix_{t['id'].lower()}.py"
        dummy_file.parent.mkdir(parents=True, exist_ok=True)
        dummy_file.write_text(f"# Preliminary setup for {t['id']}\ndef logic():\n    pass\n")
        subprocess.run(["git", "add", str(dummy_file)], cwd=project_root)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_task, project_root, t) for t in tasks]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
            t_sum = sum(res['tokens'].values()) if res['tokens'] else 0
            print(f"✅ Finished {res['id']} | Success: {res['success']} | Tokens: {t_sum}")
            
    # Summary
    summary_file = project_root / "benchmark_v1.8_results.json"
    summary_file.write_text(json.dumps(results, indent=4))
    
    all_tokens = [sum(r['tokens'].values()) for r in results if r['tokens']]
    total_tokens = sum(all_tokens)
    avg_tokens = total_tokens / len(results) if results else 0
    print(f"\n📊 Benchmark Total Tokens: {total_tokens}")
    print(f"📊 Benchmark Average Tokens: {avg_tokens:.0f}")

if __name__ == "__main__":
    run_v1_8_mega_benchmark()
