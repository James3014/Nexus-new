import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from nexus.services.continuous_learning import persist_structured_lesson
from nexus.services.lesson_retrieval import retrieve_with_resolution

async def run_simulation():
    repo_root = Path(os.getcwd())
    print(f"🚀 [ConsensusSim] Initializing Physical Simulation at {repo_root.name}...")
    
    # 1. Prepare Paths
    knowledge_dir = repo_root / ".nexus" / "knowledge"
    learning_dir = repo_root / ".nexus" / "learning"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    learning_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear existing state
    for p in [knowledge_dir / "lesson_events.jsonl", learning_dir / "shared_lessons.jsonl"]:
        if p.exists(): p.unlink()

    # TEST A: High-Consensus Injection
    print("\n📝 [Test A: High Consensus]")
    persist_structured_lesson(
        repo_root=repo_root,
        task_id="task-high-conf",
        raw_lesson="SWARM_CONSENSUS target found",
        category="LOGIC",
        root_cause="Mismatch in UTC",
        corrective_action="Use UTC normalizing",
        confidence=0.9
    )
    
    res_a = retrieve_with_resolution(repo_root, "SWARM_CONSENSUS target", diagnosis={"category": "LOGIC"})
    print(f"   - Status: {res_a['status']} | Score: {res_a.get('consensus_score', 0):.2f}")
    assert res_a["status"] == "high_consensus", "Test A FAILED: Should have high consensus."
    assert "UTC normalizing" in res_a["prompt_context"], "Test A FAILED: Context not rendered."

    # TEST B: Low-Consensus Fallback (Old Lesson + Low Conf)
    print("\n📝 [Test B: Low Consensus Fallback]")
    if (knowledge_dir / "lesson_events.jsonl").exists(): (knowledge_dir / "lesson_events.jsonl").unlink()
    
    old_ts = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    persist_structured_lesson(
        repo_root=repo_root,
        task_id="task-old",
        raw_lesson="FALLBACK_TARGET found",
        category="LOGIC",
        root_cause="Stale issue",
        corrective_action="Old fix",
        confidence=0.5, # Low confidence
        timestamp_utc=old_ts # Old
    )
    
    res_b = retrieve_with_resolution(repo_root, "FALLBACK_TARGET", diagnosis={"category": "LOGIC"})
    print(f"   - Status: {res_b['status']} | Score: {res_b.get('consensus_score', 0):.2f}")
    assert res_b["status"] == "low_consensus", "Test B FAILED: Should have triggered fallback."
    assert "Defaulting to first-principles" in res_b["prompt_context"], "Test B FAILED: Fallback prompt missing."

    print("\n🟢 Simulation SUCCESS: Consensus Engine governs and fails-closed correctly.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
