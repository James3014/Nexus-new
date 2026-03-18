#!/usr/bin/env python3
import json
import logging
from pathlib import Path
import sys
import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.core.state_io import StateIO

def main():
    project_root = Path.cwd()
    state_io = StateIO(str(project_root))
    state = state_io.load_global_state()
    
    # 🧬 WP-1 Refinement: Identify current benchmarking run or task
    latest_dir = project_root / ".nexus" / "runs" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    
    # Discovery Logic: Look for real metrics from the most recent benchmark run
    candidates = list(project_root.glob(".nexus/runs/task-*/OFF-*/phase_metrics/*_metrics.json"))
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    real_metrics = None
    source_task = state.task_id
    if candidates:
        try:
            real_metrics = json.loads(candidates[0].read_text(encoding="utf-8"))
            source_task = candidates[0].parent.parent.name # e.g. OFF-010
            print(f"📡 Discovered metrics from benchmark task: {source_task}")
        except:
             pass

    if real_metrics:
        # Robustness: support both 'phase_metrics' and 'metrics' keys
        p_metrics = real_metrics.get("phase_metrics") or real_metrics.get("metrics") or {}
        data = {
            "task_id": source_task,
            "pipeline_health": real_metrics.get("pipeline_health", 0.0),
            "timestamp": datetime.datetime.now().isoformat(),
            "phase_metrics": p_metrics
        }
    else:
        # Fallback to global state (or default)
        data = {
            "task_id": state.task_id if state.task_id != "new-task" else f"bench-{datetime.datetime.now().strftime('%Y%H%M')}",
            "pipeline_health": state.pipeline_health,
            "timestamp": datetime.datetime.now().isoformat(),
            "phase_metrics": {p: m.dict() for p, m in state.phase_metrics.items()}
        }
    
    # 🧪 WP-1 Requirement: lowest_phase_health excludes 0.0
    active_healths = [m["health"] if isinstance(m, dict) else m.health 
                      for m in data["phase_metrics"].values() 
                      if (m["health"] if isinstance(m, dict) else m.health) > 0]
    
    data["lowest_phase_health"] = min(active_healths) if active_healths else 0.0
    
    # 🧪 WP-4 Integration: Read learning_velocity if it exists
    data["learning_velocity"] = 0.0
    lv_file = project_root / ".nexus" / "learning_velocity.json"
    if lv_file.exists():
        try:
            lv_data = json.loads(lv_file.read_text(encoding="utf-8"))
            data["learning_velocity"] = lv_data.get("current", 0.0)
        except:
            pass
    
    metrics_file = latest_dir / "phase_metrics.json"
    metrics_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Phase metrics [{data['task_id']}] written to {metrics_file}")

if __name__ == "__main__":
    main()
