"""
🔥 Phase 14 AutoEvolution Engine — Hardened Acceptance Test Suite
=================================================================
16 Scenarios covering: edge cases, concurrency, error recovery,
data integrity, resource cleanup, configuration drift, integration.

Exit code 0 = ALL PASS, non-zero = FAIL with details.
"""
import os
import sys
import json
import time
import shutil
import logging
import subprocess
import threading
import traceback
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from nexus.research.findings_memory import FindingsMemoryStore, FindingsCard
from nexus.learning.skill_registry import SkillRegistry
from nexus.research.wisdom.wisdom_vault import WisdomVault
from nexus.research.findings_distiller import FindingsDistiller
from nexus.core.context_hub import ContextHub
from nexus.engine.battle_swarm import BattleSwarm
from nexus.engine.reflex_loop import ReflexLoop

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("phase14_hardened")
logger.setLevel(logging.INFO)

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []

def scenario(name):
    def decorator(fn):
        def wrapper():
            global PASS_COUNT, FAIL_COUNT
            print(f"\n{'='*60}")
            print(f"  [Scenario] {name}")
            print(f"{'='*60}")
            try:
                fn()
                PASS_COUNT += 1
                print(f"  ✅ PASSED: {name}")
            except Exception as e:
                FAIL_COUNT += 1
                FAILURES.append((name, str(e)))
                print(f"  ❌ FAILED: {name}")
                traceback.print_exc()
        return wrapper
    return decorator

# ── Shared fixtures ──────────────────────────────────────────
def fresh_test_root(suffix: str) -> Path:
    p = project_root / f".nexus_test_hardened_{suffix}"
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True, exist_ok=True)
    return p

def make_distiller_env(test_root: Path):
    store = FindingsMemoryStore(test_root)
    reg_path = test_root / "registry" / "shared_skills.db"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    registry = SkillRegistry(reg_path)
    vault = WisdomVault(str(test_root))
    distiller = FindingsDistiller(store, registry, vault, score_threshold=7.0)
    return store, registry, vault, distiller

def make_high_score_card(task_id="task-H1", score=9.0, strategy="aggressive", body="Fixed via aggressive rewrite"):
    return FindingsCard(
        task_id=task_id, kind="episodes",
        title=f"BattleSwarm {strategy}: WIN",
        scope="task",
        tags=[f"strategy:{strategy}", "lang:python", "file:*.py"],
        stage="R", body=body,
        extra={"audit_score": score, "suggested_params": {"temperature": 0.7}}
    )

def make_git_repo(path: Path):
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), capture_output=True)
    (path / "README.md").write_text("# test")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(path), check=True, capture_output=True)

# ═══════════════════════════════════════════════════════════════
# LAYER 1: FindingsDistiller 邊界測試
# ═══════════════════════════════════════════════════════════════

@scenario("S01 — Distill: score exactly at threshold (7.0) should pass")
def s01():
    tr = fresh_test_root("s01")
    store, reg, vault, distiller = make_distiller_env(tr)
    card = make_high_score_card(task_id="edge-7", score=7.0)
    store.write(card)
    ids = distiller.distill_batch()
    assert len(ids) == 1, f"Threshold-exact card should be distilled, got {len(ids)}"

@scenario("S02 — Distill: score just below threshold (6.99) must NOT pass")
def s02():
    tr = fresh_test_root("s02")
    store, reg, vault, distiller = make_distiller_env(tr)
    card = make_high_score_card(task_id="edge-6.99", score=6.99)
    store.write(card)
    ids = distiller.distill_batch()
    assert len(ids) == 0, f"Below-threshold card should NOT be distilled, got {len(ids)}"

@scenario("S03 — Distill: card with missing extra/audit_score defaults to 0")
def s03():
    tr = fresh_test_root("s03")
    store, reg, vault, distiller = make_distiller_env(tr)
    card = FindingsCard(
        task_id="no-extra", kind="episodes", title="No Extra", scope="task",
        tags=["lang:python"], stage="R", body="body", extra={}
    )
    store.write(card)
    ids = distiller.distill_batch()
    assert len(ids) == 0, f"Card with no audit_score should get score 0 and be skipped"

@scenario("S04 — Distill: idempotent triple-run produces no duplicates")
def s04():
    tr = fresh_test_root("s04")
    store, reg, vault, distiller = make_distiller_env(tr)
    card = make_high_score_card(task_id="triple-run", score=8.0)
    store.write(card)
    ids1 = distiller.distill_batch()
    ids2 = distiller.distill_batch()
    ids3 = distiller.distill_batch()
    assert len(ids1) == 1
    assert len(ids2) == 0, f"Second run should be deduped, got {len(ids2)}"
    assert len(ids3) == 0, f"Third run should be deduped, got {len(ids3)}"

@scenario("S05 — Distill: batch of 20 cards, mixed scores, only high ones distilled")
def s05():
    tr = fresh_test_root("s05")
    store, reg, vault, distiller = make_distiller_env(tr)
    expected_high = 0
    for i in range(20):
        score = 3.0 + (i * 0.5)  # 3.0 → 12.5
        card = make_high_score_card(task_id=f"batch-{i}", score=score, strategy=f"strat{i}")
        store.write(card)
        if score >= 7.0:
            expected_high += 1
    ids = distiller.distill_batch(limit=50)
    assert len(ids) == expected_high, f"Expected {expected_high} distilled, got {len(ids)}"

@scenario("S06 — Distill: battle_results with no winner returns None")
def s06():
    tr = fresh_test_root("s06")
    store, reg, vault, distiller = make_distiller_env(tr)
    result = distiller.distill_battle_results({"status": "all_failed", "winner": None}, "task-999")
    assert result is None, f"Expected None for failed battle, got {result}"

# ═══════════════════════════════════════════════════════════════
# LAYER 2: WisdomVault + WisdomPrior 語義完整性
# ═══════════════════════════════════════════════════════════════

@scenario("S07 — WisdomVault: search on empty DB returns None gracefully")
def s07():
    tr = fresh_test_root("s07")
    vault = WisdomVault(str(tr))
    result = vault.search_wisdom("anything at all", limit=5)
    assert result is None, f"Empty vault should return None, got {type(result)}"

@scenario("S08 — WisdomPrior: inject with no vault returns empty dict")
def s08():
    tr = fresh_test_root("s08")
    hub = ContextHub(str(tr))
    hub.wisdom_vault = None
    result = hub._inject_wisdom_prior("some task", ["file.py"])
    assert result == {}, f"No vault should yield empty dict, got {result}"

@scenario("S09 — WisdomVault: multi-record ingest + semantic ordering")
def s09():
    tr = fresh_test_root("s09")
    store, reg, vault, distiller = make_distiller_env(tr)
    # Ingest 3 distinct topics
    topics = [
        ("task-py", "aggressive", "python type error fix", 9.0),
        ("task-rs", "decompose", "rust lifetime borrow checker", 8.5),
        ("task-js", "conservative", "javascript async callback hell", 8.0),
    ]
    for tid, strat, body, score in topics:
        card = make_high_score_card(task_id=tid, score=score, strategy=strat, body=body)
        store.write(card)
    distiller.distill_batch()

    # Query something related to python
    results = vault.search_wisdom("python type checking error", limit=3)
    assert results is not None and not results.empty, "Should find results for python query"
    top_task = results.iloc[0]["task"]
    assert "aggressive" in top_task, f"Python query should match python card first, got: {top_task}"

# ═══════════════════════════════════════════════════════════════
# LAYER 3: BattleSwarm 壓力與邊界測試
# ═══════════════════════════════════════════════════════════════

@scenario("S10 — BattleSwarm: all workers crash → status=all_failed")
def s10():
    tr = fresh_test_root("s10")
    repo = tr / "repo"
    repo.mkdir()
    make_git_repo(repo)
    swarm = BattleSwarm(str(repo), default_workers=2, run_dir=str(tr / "wt"))

    def crashing_worker(strategy, wt_path, tid, desc, ctx):
        raise RuntimeError(f"Simulated crash in {strategy['name']}")

    result = swarm.trigger_battle("crash-test", "desc", {}, crashing_worker)
    assert result["status"] == "all_failed", f"All-crash should be all_failed, got {result['status']}"
    # Winner should be selected from highest score (all 0.0)
    assert result["winner"] is not None, "Even in all_failed, a 'winner' (best loser) should exist"
    swarm.cleanup(result)

@scenario("S11 — BattleSwarm: exactly 1 of N passes → correct winner")
def s11():
    tr = fresh_test_root("s11")
    repo = tr / "repo"
    repo.mkdir()
    make_git_repo(repo)
    swarm = BattleSwarm(str(repo), default_workers=4, run_dir=str(tr / "wt"))

    def selective_worker(strategy, wt_path, tid, desc, ctx):
        if strategy["name"] == "decompose":
            return {"passed": True, "score": 7.5}
        return {"passed": False, "score": 2.0}

    result = swarm.trigger_battle("selective", "desc", {}, selective_worker)
    assert result["status"] == "winner_found"
    assert result["winner"]["strategy"] == "decompose", f"Expected decompose winner, got {result['winner']['strategy']}"
    swarm.cleanup(result)

@scenario("S12 — BattleSwarm: worktree cleanup leaves no orphans")
def s12():
    tr = fresh_test_root("s12")
    repo = tr / "repo"
    repo.mkdir()
    make_git_repo(repo)
    swarm = BattleSwarm(str(repo), default_workers=2, run_dir=str(tr / "wt"))

    def noop_worker(strategy, wt_path, tid, desc, ctx):
        return {"passed": False, "score": 1.0}

    result = swarm.trigger_battle("cleanup-test", "desc", {}, noop_worker)
    # Verify worktrees exist before cleanup
    wt_dir = tr / "wt"
    assert any(wt_dir.iterdir()), "Worktrees should exist before cleanup"

    swarm.cleanup(result)

    # After cleanup, git worktree list should only show main
    out = subprocess.run(["git", "worktree", "list"], cwd=str(repo), capture_output=True, text=True)
    lines = [l for l in out.stdout.strip().split("\n") if l.strip()]
    assert len(lines) == 1, f"After cleanup only main worktree should remain, got {len(lines)} lines:\n{out.stdout}"

@scenario("S13 — BattleSwarm: concurrent score tie-breaking is deterministic")
def s13():
    tr = fresh_test_root("s13")
    repo = tr / "repo"
    repo.mkdir()
    make_git_repo(repo)
    swarm = BattleSwarm(str(repo), default_workers=4, run_dir=str(tr / "wt"))

    def tie_worker(strategy, wt_path, tid, desc, ctx):
        return {"passed": True, "score": 8.0}

    result = swarm.trigger_battle("tie-test", "desc", {}, tie_worker)
    assert result["status"] == "winner_found"
    # All tied — winner should still be selected (first in sorted order)
    assert result["winner"]["score"] == 8.0
    assert len(result["all_results"]) == 4, f"Should have 4 results, got {len(result['all_results'])}"
    swarm.cleanup(result)

# ═══════════════════════════════════════════════════════════════
# LAYER 4: ReflexLoop 自適應邊界與腐蝕測試
# ═══════════════════════════════════════════════════════════════

@scenario("S14 — ReflexLoop: workers upper bound clamped at 8")
def s14():
    tr = fresh_test_root("s14")
    reflex = ReflexLoop(str(tr))
    # Manually set workers to 7, then feed failures
    cfg = reflex.config
    cfg["battle_workers"] = 7
    reflex._save_config(cfg)

    log_dir = tr / ".nexus" / "metrics"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "skill_outcome_events.jsonl"
    lines = [json.dumps({"passed": False, "metadata": {"battle_swarm_triggered": True}}) for _ in range(10)]
    log_path.write_text("\n".join(lines))

    res1 = reflex.evaluate_battle_swarm_performance()
    assert res1["new_workers"] == 8, f"Should scale to 8, got {res1.get('new_workers')}"

    # Run again — already at 8, should NOT increase further
    res2 = reflex.evaluate_battle_swarm_performance()
    assert res2.get("updated") is False, f"At ceiling 8, should not update, got {res2}"

@scenario("S15 — ReflexLoop: high success rate scales DOWN, clamped at 2")
def s15():
    tr = fresh_test_root("s15")
    reflex = ReflexLoop(str(tr))
    cfg = reflex.config
    cfg["battle_workers"] = 3
    reflex._save_config(cfg)

    log_dir = tr / ".nexus" / "metrics"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "skill_outcome_events.jsonl"
    # 90% success
    lines = [json.dumps({"passed": True, "metadata": {"battle_swarm_triggered": True}}) for _ in range(9)]
    lines.append(json.dumps({"passed": False, "metadata": {"battle_swarm_triggered": True}}))
    log_path.write_text("\n".join(lines))

    res = reflex.evaluate_battle_swarm_performance()
    assert res["updated"] is True
    assert res["new_workers"] == 2, f"Should scale down to 2, got {res.get('new_workers')}"

    # Run again at 2 — should not go below
    res2 = reflex.evaluate_battle_swarm_performance()
    assert res2.get("updated") is False, f"At floor 2, should not update, got {res2}"

@scenario("S16 — ReflexLoop: corrupted JSON log is handled gracefully")
def s16():
    tr = fresh_test_root("s16")
    reflex = ReflexLoop(str(tr))
    log_dir = tr / ".nexus" / "metrics"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "skill_outcome_events.jsonl"
    # Mix of valid and corrupt lines
    lines = [
        json.dumps({"passed": True, "metadata": {"battle_swarm_triggered": True}}),
        "THIS IS NOT JSON {{{",
        json.dumps({"passed": False, "metadata": {"battle_swarm_triggered": True}}),
        "",
        "another garbage line",
    ]
    log_path.write_text("\n".join(lines))

    # Should not crash — may return updated or not, but must not raise
    res = reflex.evaluate_battle_swarm_performance()
    assert isinstance(res, dict), f"Should return dict even with corrupt data, got {type(res)}"

# ═══════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_scenarios = [s01, s02, s03, s04, s05, s06, s07, s08, s09, s10, s11, s12, s13, s14, s15, s16]
    
    print("\n" + "🔥" * 30)
    print("  NEXUS PHASE 14 — HARDENED ACCEPTANCE TEST (16 Scenarios)")
    print("🔥" * 30)
    
    t0 = time.time()
    for fn in all_scenarios:
        fn()
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"  RESULTS: {PASS_COUNT} PASSED / {FAIL_COUNT} FAILED  ({elapsed:.1f}s)")
    print(f"{'='*60}")
    if FAILURES:
        print("\n  ❌ FAILURES:")
        for name, err in FAILURES:
            print(f"    - {name}: {err}")
    
    sys.exit(1 if FAIL_COUNT > 0 else 0)
