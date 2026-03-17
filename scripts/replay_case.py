#!/usr/bin/env python3
import sys
import json
import argparse
import time
from pathlib import Path

# Ensure project imports work
sys.path.append(str(Path.cwd()))

from nexus.engine.coordinator import NexusEngine
from nexus.core.state_io import StateIO

def replay_case(case_id: str):
    project_root = Path.cwd()
    catalog_path = project_root / "cases" / "catalog.json"
    
    if not catalog_path.exists():
        print(f"❌ Catalog not found at {catalog_path}")
        return

    catalog = json.loads(catalog_path.read_text())
    case_meta = next((c for c in catalog["cases"] if c["id"] == case_id), None)
    
    if not case_meta:
        print(f"❌ Case {case_id} not found in catalog.")
        return

    case_file = project_root / "cases" / case_meta["file"]
    if not case_file.exists():
        print(f"❌ Case file {case_file} missing.")
        return

    case_data = json.loads(case_file.read_text())
    print(f"🎬 [Replay] Starting Case: {case_id} ({case_data['goal']})")

    # Setup isolated run directory
    run_dir = project_root / ".nexus" / "replays" / case_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Standard DI Setup (v1.8 Core)
    from nexus.containers import NexusContainer
    container = NexusContainer()
    container.project_root.from_value(str(project_root))
    
    # Initialize Engine via Container
    engine = container.engine_factory(
        project_root=project_root,
        run_dir=run_dir,
        silent=True
    )
    
    # Override state_io to use replay location
    state_file = run_dir / "replay_state.jsonl"
    state_io = container.state_io(state_file=str(state_file))
    engine.state_io = state_io
    
    start_time = time.time()
    success = False
    
    try:
        if case_meta["type"] == "bug":
            success = engine.run_bug(case_id, desc=case_data["goal"])
        else:
            success = engine.run_feature(case_data["goal"])
    except Exception as e:
        print(f"💥 [Replay] Execution Failed: {e}")
    
    duration = time.time() - start_time
    
    # Validation
    expected = case_data.get("expected_outcome", {})
    final_state = state_io.load_global_state()
    history_phases = [h.phase for h in final_state.steps_history]
    
    print(f"\n📊 [Replay Results: {case_id}]")
    print(f"⏱️  Duration: {duration:.2f}s")
    print(f"✅ Success: {success}")
    print(f"🛣️  Phases Reached: {' -> '.join(history_phases)}")
    
    # Simple Gate Check
    if all(p in history_phases for p in expected.get("phases", [])):
        print("🎉 [MATCH] All required phases reached.")
    else:
        print("⚠️ [MISMATCH] Some expected phases were skipped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nexus Offline Case Replayer")
    parser.add_argument("case_id", help="ID of the case to replay (e.g., OFF-001)")
    args = parser.parse_args()
    
    replay_case(args.case_id)
