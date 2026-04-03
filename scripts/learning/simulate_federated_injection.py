import asyncio
import json
import os
from pathlib import Path
from nexus.services.continuous_learning import persist_structured_lesson
from nexus.services.lesson_retrieval import retrieve_enhanced_lessons, inject_lesson_context

async def run_simulation():
    repo_root = Path(os.getcwd())
    print(f"🚀 [SwarmSim] Initializing Physical Simulation at {repo_root.name}...")
    
    # 1. Prepare Paths
    knowledge_dir = repo_root / ".nexus" / "knowledge"
    learning_dir = repo_root / ".nexus" / "learning"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    learning_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear existing state for clean sim
    for p in [knowledge_dir / "lesson_events.jsonl", learning_dir / "shared_lessons.jsonl"]:
        if p.exists(): p.unlink()

    # 2. Add Local Lesson (Low match)
    persist_structured_lesson(
        repo_root=repo_root,
        task_id="task-local",
        raw_lesson="Baseline fix",
        category="LOGIC",
        root_cause="Minor mismatch",
        corrective_action="Fix baseline"
    )
    print("✅ [SwarmSim] Local truth record injected.")

    # 3. Add Shared Envelope (High match)
    shared_envelope = {
        "cache_id": "cache-abc",
        "lesson": {
            "lesson_id": "sha-shared",
            "task_id": "task-shared",
            "category": "ARCH",
            "root_cause": "SWARM_TARGET found", # TARGET WORD
            "corrective_action": "Inject swarm intelligence",
            "confidence": 0.95,
            "timestamp_utc": "2026-04-03T12:00:00Z",
            "schema_version": "lesson_event.v1",
            "outcome": "success"
        },
        "source_type": "p2p",
        "source_repo": "ws-alpha",
        "trust_tier": "peer",
        "local_weight": 0.85,
        "fetched_at_utc": "2026-04-03T13:00:00Z"
    }
    with open(learning_dir / "shared_lessons.jsonl", "w") as f:
        f.write(json.dumps(shared_envelope) + "\n")
    print("✅ [SwarmSim] Federated envelope injected into cache.")

    # 4. Simulate Retrieval (Search for SWARM_TARGET)
    print("🔍 [SwarmSim] Running Enhanced Retrieval...")
    retrieved = retrieve_enhanced_lessons(
        repo_root, 
        "SWARM_TARGET found in logic", 
        diagnosis={"category": "ARCH"},
        use_federated=True
    )
    
    # 5. Assertions
    print(f"📊 Results Found: {len(retrieved)}")
    for r in retrieved:
        print(f"   - Lesson: {r['task_id']} | Source: {r['_memory_source']} | Score: {r['_final_score']:.3f} | Trust: {r['_trust_weight']}")

    assert len(retrieved) >= 1, "Simulation FAILED: No lessons found."
    assert retrieved[0]["_memory_source"] == "shared", "Simulation FAILED: Shared lesson not prioritized by score."
    assert retrieved[0]["_trust_weight"] == 0.85, "Simulation FAILED: Trust penalty not applied."

    # 6. Verify Context Injection
    state = {"metadata": {}}
    _, tokens = inject_lesson_context(state, retrieved)
    
    print("\n📝 [Prompt Metadata]:")
    print(json.dumps(state["metadata"]["retrieved_lessons"], indent=2))
    
    print("\n🟢 Simulation SUCCESS: Federated Intelligence correctly governed and injected.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
