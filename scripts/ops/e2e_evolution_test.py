import sys
import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any

# Ensure nexus is in path
sys.path.append(str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

@dataclass
class MockState:
    task_id: str
    metadata: Dict[str, Any]

def run_e2e_evolution_test():
    root = Path(__file__).parent.parent.parent
    nexus_dir = root / ".nexus"
    knowledge_dir = root / ".nexusknowledge"
    
    print("\n========================================================")
    print("🛸 [Nexus v0.9] E2E Evolutionary Loop Verification")
    print("========================================================\n")

    # [1] PRE-CONDITION: Task Initialization & False Belief Formation
    task_id = f"task-E2E-TEST-{int(time.time())}"
    print(f"👉 Step 1: Simulating Task [{task_id}]")
    
    from nexus.services.mem_palace import MemPalace
    palace = MemPalace(str(root))
    
    # Simulate agent forming a belief that led to failure
    test_belief_id = f"B-{task_id}"
    false_belief_content = f"I erroneously believe port 8080 is always open for {task_id}."
    
    # Manually seeding belief into LanceDB for MemPalace
    import lancedb
    db = lancedb.connect(str(nexus_dir / "vector_db"))
    res = db.list_tables()
    tables = res if isinstance(res, list) else getattr(res, "tables", res)
    
    if "nexus_soul_palace" not in tables:
        db.create_table("nexus_soul_palace", data=[{"id": "dummy", "task": "dummy", "content": "dummy", "status": "active", "vector": [0.0]*384, "updated_at": "now"}])
    
    table = db.open_table("nexus_soul_palace")
    table.add([{
        "id": test_belief_id,
        "wing": "CORE",
        "room": "GENERAL",
        "type": "belief",
        "content": false_belief_content,
        "layer": 1,
        "status": "active",
        "timestamp": "2026-04-09T00:00:00Z",
        "vector": [0.05] * 384
    }])
    
    # Also write to jsonl
    beliefs_path = knowledge_dir / "beliefs.jsonl"
    with open(beliefs_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({"id": test_belief_id, "task": task_id, "content": false_belief_content, "status": "active"}) + '\n')
        
    print(f"   ✔️ Pre-seeded FALSE Belief into MemPalace: {test_belief_id} (Status: ACTIVE)")
    
    # [2] EXECUTION: Simulate Task Failure
    print(f"\n👉 Step 2: Task failed due to false belief. Triggering Continuous Learning Loop...")
    mock_state = MockState(
        task_id=task_id, 
        metadata={"cycle_root_cause": "Port 8080 was blocked by firewall. Assumption was invalid."}
    )
    
    from nexus.services.continuous_learning import finalize_learning_loop
    
    # This should trigger Lesson Extraction, Memory Indexing (incremental merge), and Belief Revision
    finalize_learning_loop(root, mock_state, success=False, source="e2e-verifier")
    
    # [3] VERIFICATION
    print(f"\n👉 Step 3: Verifying the 3 Memory Systems")
    verification_passed = True
    
    # System 1: Base Memory (Local Storage)
    print("\n   [Sys 1: Base Memory - Fault Records]")
    fault_log = root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    found_fault = False
    with open(fault_log, "r") as f:
        for line in reversed(f.readlines()):
            record = json.loads(line)
            if record.get("task_id") == task_id:
                found_fault = True
                print(f"   ✅ SUCCESS: Captured exact Root Cause -> {record.get('root_cause') or record.get('category') or 'Found Event'}")
                break
    if not found_fault:
        print("   ❌ FAIL: Fault record not found.")
        verification_passed = False

    # System 2: Belief System (MemPalace / Soul)
    print("\n   [Sys 2: MemPalace - Belief Revision]")
    found_revision = False
    with open(beliefs_path, "r") as f:
        for line in reversed(f.readlines()):
            record = json.loads(line)
            if record.get("id") == test_belief_id:
                if record.get("status") == "superseded":
                    found_revision = True
                    print(f"   ✅ SUCCESS: Belief {test_belief_id} was automatically flagged as 'superseded'.")
                else:
                    print(f"   ❌ FAIL: Belief status is still {record.get('status')}")
                break
    if not found_revision:
        verification_passed = False
        
    # System 3: Wisdom Layer (LanceDB Index)
    print("\n   [Sys 3: Wisdom Layer - LanceDB Incremental Index]")
    try:
        import lancedb
        db = lancedb.connect(str(root / ".nexus" / "memory" / "memory_index.lancedb"))
        table = db.open_table("memory_index")
        df = table.to_pandas()
        matched_df = df[df['task_id'] == task_id]
        if not matched_df.empty:
            print(f"   ✅ SUCCESS: New lesson dynamically indexed into LanceDB via merge_insert!")
            print(f"      Matched Record excerpt: {matched_df.iloc[0]['payload_json'][:100]}...")
        else:
            print(f"   ❌ FAIL: Lesson not found in LanceDB index. Incremental indexing might have failed.")
            verification_passed = False
    except Exception as e:
        print(f"   ❌ FAIL: LanceDB verification threw an error: {e}")
        verification_passed = False

    print("\n========================================================")
    if verification_passed:
        print("🏆 RESULT: 100% SUCCESS. The System is FULLY ALIVE and EVOLVING autonomously.")
    else:
        print("💀 RESULT: FAILED. The Evolutionary Loop is broken.")
    print("========================================================\n")
    
if __name__ == "__main__":
    run_e2e_evolution_test()
