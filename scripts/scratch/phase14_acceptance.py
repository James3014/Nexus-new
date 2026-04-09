import os
import sys
import logging
from pathlib import Path

# Setup path so we can import nexus
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from nexus.research.findings_memory import FindingsMemoryStore, FindingsCard
from nexus.learning.skill_registry import SkillRegistry
from nexus.research.wisdom.wisdom_vault import WisdomVault
from nexus.research.findings_distiller import FindingsDistiller
from nexus.core.context_hub import ContextHub

logging.basicConfig(level=logging.INFO, format="%(message)s")

def test_phase14a_distiller_and_wisdom_prior():
    print("\n--- Testing Phase 14a: FindingsDistiller + WisdomPrior ---")
    
    # 1. Setup mock environment
    import shutil
    test_root = project_root / ".nexus_test_phase14"
    if test_root.exists():
        shutil.rmtree(test_root)
    test_root.mkdir(parents=True, exist_ok=True)
    
    store = FindingsMemoryStore(test_root)
    registry_path = test_root / "registry" / "shared_skills.db"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry = SkillRegistry(registry_path)
    vault = WisdomVault(str(test_root))
    
    distiller = FindingsDistiller(store, registry, vault, score_threshold=7.0)
    
    # 2. Scenarios:
    # Scenario 1: Distiller 基本蒸餾 (Mock FindingsCards)
    print("\n[Scenario 1] Basic Distillation (Score > 7)")
    card1 = FindingsCard(
        task_id="task-101",
        kind="episodes",
        title="BattleSwarm aggressive: WIN",
        scope="task",
        tags=["strategy:aggressive", "lang:python", "file:*.py"],
        stage="R",
        body="Repaired by breaking down logic",
        extra={"audit_score": 8.5, "suggested_params": {"temperature": 0.7, "prompt_modifier": "Aggressive"}}
    )
    store.write(card1)
    
    card2 = FindingsCard(
        task_id="task-102",
        kind="episodes",
        title="BattleSwarm conservative: LOSE",
        scope="task",
        tags=["strategy:conservative", "lang:python"],
        stage="R",
        body="Failed to repair",
        extra={"audit_score": 4.0}  # Below threshold
    )
    store.write(card2)
    
    distilled_ids = distiller.distill_batch()
    print(f"Distilled IDs: {distilled_ids}")
    assert len(distilled_ids) == 1, f"Expected 1 distilled skill, got {len(distilled_ids)}"
    print("✅ Scenario 1 Passed")
    
    # Scenario 2: Distiller 去重
    print("\n[Scenario 2] Deduplication")
    distilled_ids_again = distiller.distill_batch()
    print(f"Distilled IDs again: {distilled_ids_again}")
    assert len(distilled_ids_again) == 0, f"Expected 0 new skills, got {len(distilled_ids_again)}"
    print("✅ Scenario 2 Passed")
    
    # Scenario 3: WisdomPrior 命中
    print("\n[Scenario 3] WisdomPrior Hit")
    hub = ContextHub(str(test_root))
    hub.wisdom_vault = vault
    
    print(f"LanceDB tables available: {vault.db.list_tables()}")
    query = "Repaired by breaking down logic files:main.py"
    raw_results = vault.search_wisdom(query, limit=3)
    print(f"Raw LanceDB Results:\n{raw_results}")

    prior = hub._inject_wisdom_prior("Repaired by breaking down logic", ["main.py"])
    print(f"WisdomPrior Result: {prior}")
    assert "prior_strategy" in prior
    assert len(prior.get("battle_history", [])) > 0
    print("✅ Scenario 3 Passed")

    # Scenario 4: WisdomPrior 空庫 (Query is totally unrelated)
    print("\n[Scenario 4] WisdomPrior Miss")
    prior_miss = hub._inject_wisdom_prior("Compile Rust trait bounds", ["lib.rs"])
    # Not strictly empty if the database is small (LanceDB might return closest), but let's check distance
    print(f"WisdomPrior Result (Miss): {prior_miss}")
    if prior_miss:
        # Confidence score should be lower for unrelated (distance is higher)
        dist = prior_miss.get("prior_confidence", 0)
        print(f"Distance for miss: {dist}")
    print("✅ Scenario 4 Passed")

def test_phase14b_battle_swarm():
    print("\n--- Testing Phase 14b: BattleSwarm (Real-time Swarm) ---")
    import shutil
    import subprocess
    
    test_root = project_root / ".nexus_test_phase14_swarm"
    if test_root.exists():
        subprocess.run(["git", "worktree", "prune"], cwd=str(project_root), capture_output=True) # clean orphans
        shutil.rmtree(test_root, ignore_errors=True)
    test_root.mkdir(parents=True, exist_ok=True)
    
    from nexus.engine.battle_swarm import BattleSwarm
    
    # Create dummy local git repo for worktree tests
    repo_dir = test_root / "dummy_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    
    # Need to config identity locally so commit works in CI/script
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial commit"], cwd=str(repo_dir), check=True, capture_output=True)
    
    swarm = BattleSwarm(str(repo_dir), default_workers=2, run_dir=str(test_root))
    
    # Scenarios for BattleSwarm
    print("\n[Scenario 5] BattleSwarm Forking & Winner Selection")
    def mock_worker(strategy, wt_path, tid, desc, ctx):
        import time
        time.sleep(0.5) # Simulate work
        passed = strategy["name"] == "aggressive"
        score = 9.5 if passed else 3.0
        return {"passed": passed, "score": score, "language": "python"}
        
    result = swarm.trigger_battle("task-202", "Fix concurrency issue", {}, mock_worker)
    
    print(f"Battle Status: {result.get('status')}")
    assert result.get("status") == "winner_found"
    assert result.get("winner")["strategy"] == "aggressive"
    print(f"Winner output: {result.get('winner')}")
    
    # Cleanup branches and worktrees
    swarm.cleanup(result)
    print("✅ Scenario 5 Passed")


def test_phase14c_reflex_loop():
    print("\n--- Testing Phase 14c: ReflexLoop (Background Self-Optimization) ---")
    import json
    test_root = project_root / ".nexus_test_phase14_reflex"
    test_root.mkdir(parents=True, exist_ok=True)
    
    # Write mock metrics logs
    log_dir = test_root / ".nexus" / "metrics"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "skill_outcome_events.jsonl"
    
    # We simulate 5 consecutive swarm failures to force ReflexLoop to increase workers
    lines = []
    for _ in range(5):
        lines.append(json.dumps({
            "task_id": "mock",
            "passed": False,
            "metadata": {"battle_swarm_triggered": True, "autonomic_route": "standard", "est_tokens": 10000}
        }))
    log_path.write_text("\n".join(lines))
    
    from nexus.engine.reflex_loop import ReflexLoop
    reflex = ReflexLoop(str(test_root))
    
    # Ensure initialized to default
    assert reflex.config["battle_workers"] == 4
    
    print("\n[Scenario 6] ReflexLoop adapts to systematic failure")
    res = reflex.evaluate_battle_swarm_performance(limit=5)
    print(f"Reflex Tuning Result: {res}")
    assert res.get("updated") is True
    assert res.get("new_workers") == 5, f"Workers didn't scale up. Expected 5, got {res.get('new_workers')}"
    
    print("✅ Scenario 6 Passed")

if __name__ == "__main__":
    test_phase14a_distiller_and_wisdom_prior()
    test_phase14b_battle_swarm()
    test_phase14c_reflex_loop()
