#!/usr/bin/env python3
import datetime
import json
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.core.state_io import StateIO


SECTION_START = "<!-- NEXUS_PHASE_METRICS:START -->"
SECTION_END = "<!-- NEXUS_PHASE_METRICS:END -->"


def _normalize_phase_metrics(raw_phase_metrics):
    normalized = {}
    for phase in ("P", "X", "D", "R", "A", "C"):
        metric = raw_phase_metrics.get(phase, {})
        if hasattr(metric, "dict"):
            metric = metric.dict()
        signals = dict(metric.get("signals") or {})
        if phase == "X":
            latency = signals.get("research_latency")
            if latency is None and signals.get("research_latency_norm") is not None:
                latency = signals.get("research_latency_norm")
            if latency is not None:
                signals["research_latency"] = float(latency)
        normalized[phase] = {
            "health": float(metric.get("health", 0.0)),
            "signals": signals,
        }
    return normalized


def _render_live_status_section(data):
    phase_metrics = data["phase_metrics"]
    lines = [
        SECTION_START,
        "## Nexus Phase Metrics (Auto Sync)",
        f"- Updated: `{data['timestamp']}`",
        f"- Task: `{data['task_id']}`",
        f"- Pipeline Health: `{float(data['pipeline_health']):.2f}`",
        f"- Lowest Phase Health: `{float(data['lowest_phase_health']):.2f}`",
        f"- Learning Velocity: `{float(data.get('learning_velocity', 0.0)):+.2f}`",
        "",
        "| Phase | Health |",
        "| --- | ---: |",
    ]
    for phase in ("P", "X", "D", "R", "A", "C"):
        health = float(phase_metrics.get(phase, {}).get("health", 0.0))
        lines.append(f"| `{phase}` | `{health:.2f}` |")
    lines.append(SECTION_END)
    return "\n".join(lines)


def _update_exec_live_status(project_root: Path, data: dict):
    status_file = project_root / "docs" / "EXEC_LIVE_STATUS.md"
    if not status_file.exists():
        return
    content = status_file.read_text(encoding="utf-8")
    section = _render_live_status_section(data)
    pattern = re.compile(
        re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END),
        flags=re.DOTALL,
    )
    if pattern.search(content):
        content = pattern.sub(section, content, count=1)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += "\n" + section + "\n"
    status_file.write_text(content, encoding="utf-8")

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
            "phase_metrics": _normalize_phase_metrics(p_metrics),
        }
    else:
        # Fallback to global state (or default)
        data = {
            "task_id": state.task_id if state.task_id != "new-task" else f"bench-{datetime.datetime.now().strftime('%Y%H%M')}",
            "pipeline_health": state.pipeline_health,
            "timestamp": datetime.datetime.now().isoformat(),
            "phase_metrics": _normalize_phase_metrics({p: m.model_dump() for p, m in state.phase_metrics.items()}),
        }
    
    # 🧪 WP-1 Requirement: lowest_phase_health excludes 0.0
    active_healths = [m["health"] if isinstance(m, dict) else m.health 
                      for m in data["phase_metrics"].values() 
                      if (m["health"] if isinstance(m, dict) else m.health) > 0]
    
    data["lowest_phase_health"] = min(active_healths) if active_healths else 0.0
    
    # 🧪 WP-4 Integration: Read learning_velocity if it exists
    data["learning_velocity"] = float(state.learning_velocity or 0.0)
    lv_file = project_root / ".nexus" / "learning_velocity.json"
    if lv_file.exists() and abs(data["learning_velocity"]) < 1e-9:
        try:
            lv_data = json.loads(lv_file.read_text(encoding="utf-8"))
            data["learning_velocity"] = lv_data.get("current", 0.0)
        except:
            pass
    
    metrics_file = latest_dir / "phase_metrics.json"
    metrics_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Spec contract: also persist under .nexus/runs/<run_id>/phase_metrics.json
    run_id = data["task_id"] if data.get("task_id") else "latest"
    if run_id == "new-task":
        run_id = "latest"
    run_dir = project_root / ".nexus" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_metrics_file = run_dir / "phase_metrics.json"
    run_metrics_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Spec contract: real-time dashboard sync.
    _update_exec_live_status(project_root, data)
    print(f"✅ Phase metrics [{data['task_id']}] written to {metrics_file} and {run_metrics_file}")

if __name__ == "__main__":
    main()
