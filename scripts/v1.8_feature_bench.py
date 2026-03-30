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


def execute_feature_task(service: NexusCommandService, task: dict) -> bool:
    return service.execute_feature(
        task["desc"],
        delivery_mode="standard",
    )

def run_feature_task(project_root, task):
    print(f"🚀 [Feature] Starting {task['id']}...")
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
        success = execute_feature_task(service, task)
    except Exception as e:
        print(f"❌ [Feature] {task['id']} Crashed: {e}")
        success = False
        
    duration = time.time() - start_time
    
    # Load final state for metrics
    final_state = state_io.load_global_state()
    tokens = final_state.phase_tokens if hasattr(final_state, "phase_tokens") else {}
    history = final_state.steps_history if hasattr(final_state, "steps_history") else []
    
    # Heuristic Scoring (Auto)
    score = 0
    # 1. Flow to C (20 pts)
    if any(h.phase == "C" for h in history): score += 20
    # 2. Audit 1st pass (20 pts)
    r_phases = [h for h in history if h.phase == "R"]
    if len(r_phases) == 1: score += 20
    # 3. Plan has 5+ steps (15 pts) - check metadata for plan
    p_phase = next((h for h in history if h.phase == "P"), None)
    plan = p_phase.metadata.get("plan", []) if p_phase else []
    if len(plan) >= 5: score += 15
    # 4. Research applied (15 pts)
    if any(h.phase == "X" for h in history): score += 15
    # 5. Multi-file (15 pts)
    files_changed = set()
    for h in history:
        files = h.metadata.get("files", [])
        for f in files: files_changed.add(f)
    if len(files_changed) > 1: score += 15
    # 6. Lessons non-empty (15 pts)
    lessons_file = project_root / ".nexus_lessons.jsonl" # Corrected path
    if lessons_file.exists() and lessons_file.stat().st_size > 0: score += 15

    print(f"DEBUG [{task['id']}]: Phases reached: {[h.phase for h in history]} | Score: {score}")

    return {
        "id": task['id'],
        "success": success,
        "duration": duration,
        "tokens": tokens,
        "score": score,
        "phases": [h.phase for h in history],
        "files_count": len(files_changed)
    }

def run_v1_8_feature_benchmark():
    project_root = Path("/Users/jameschen/Downloads/Muse-Nexus")
    
    tasks = [
        {"id": "FEAT-401", "desc": "新增 /api/users/{id}/profile endpoint，支持 GET/PUT user profile，包含 email、avatar 欄位驗證，加 Swagger doc。"},
        {"id": "FEAT-402", "desc": "整合 Stripe v12 SDK 到 payment service，加 subscription webhook handler，包含 idempotency key，寫 unit test。"},
        {"id": "FEAT-403", "desc": "加 user_preferences JSONField 到 users table，寫 Alembic migration，更新所有相關 query，加 index。"},
        {"id": "FEAT-404", "desc": "新增 React dashboard page 呼叫 /api/analytics，後端加 aggregation endpoint，前端用 TanStack Query cache，加 e2e test。"},
        {"id": "FEAT-405", "desc": "實作 real-time chat 用 WebSocket + Redis pub/sub，包含 auth middleware、rate limit，加 load test script。"},
    ]
    
    print(f"🔥 Starting v1.8 Parallel Feature Benchmark (5 Tasks)...")
    
    # Pre-setup dummy files for each feature
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        dummy_file = src_dir / f"feat_{t['id'].lower()}.py"
        dummy_file.write_text(f"# Logic for {t['id']}\n")
        subprocess.run(["git", "add", str(dummy_file)], cwd=project_root)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_feature_task, project_root, t) for t in tasks]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
            t_sum = sum(res['tokens'].values()) if res['tokens'] else 0
            print(f"✅ Finished {res['id']} | Score: {res['score']} | Tokens: {t_sum}")
            
    # Summary Report
    report_file = project_root / "feature_benchmark_results.json"
    report_file.write_text(json.dumps(results, indent=4))
    
    total_score = sum(r['score'] for r in results)
    avg_score = total_score / len(results) if results else 0
    print(f"\n📊 Benchmark Total Score: {total_score}")
    print(f"📊 Benchmark Average Score: {avg_score:.1f}")

if __name__ == "__main__":
    run_v1_8_feature_benchmark()
