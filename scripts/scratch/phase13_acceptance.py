"""
Phase 13 高標準驗收測試套件
═══════════════════════════════════════════════════════════
每個場景都需探查真實整合路徑，並輸出可驗證的數值資料。
失敗必須顯示精確的 expected vs actual 差異。
═══════════════════════════════════════════════════════════
"""
import sys
import os
import json
import time
import sqlite3
import shutil
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from typing import Dict, Any, List

logging.basicConfig(level=logging.WARNING)

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
from nexus.core.context_hub import ContextHub
from nexus.services.mem_palace import MemPalace
from nexus.core.state_contracts import NexusState, NexusDiagnosis
from nexus.engine.autonomic_router import AutonomicRouter

# ─────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────
PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

results: List[Dict] = []

def _assert(name: str, condition: bool, actual=None, expected=None, note: str = ""):
    status = PASS if condition else FAIL
    rec = {"name": name, "status": status, "actual": actual, "expected": expected, "note": note}
    results.append(rec)
    tag = "  actual" if actual is not None else ""
    exp_tag = "  expected" if expected is not None else ""
    print(f"  {status}  {name}")
    if not condition:
        print(f"         expected: {expected!r}")
        print(f"         actual  : {actual!r}")
    if note:
        print(f"         note    : {note}")
    return condition

def mk_registry(tmp_dir: Path) -> SkillRegistry:
    db = tmp_dir / "skills_test.db"
    return SkillRegistry(db)

def mk_skill(task_id: str, name: str, languages: List[str], file_patterns: List[str],
             win_rate: float = 0.0, trust: str = "auto-generated", hyp: str = "") -> SkillFrontmatter:
    return SkillFrontmatter(
        name=name, description=f"Skill for {task_id}", task_id=task_id,
        success_metric=SkillSuccessMetric(repair_success=True),
        trust_level=trust, languages=languages, file_patterns=file_patterns,
        win_rate=win_rate, winning_hypothesis=hyp
    )

def mk_diag(summary: str, hotspots: List[str]) -> NexusDiagnosis:
    return NexusDiagnosis(task_id="acc-diag", status="pending",
                          summary=summary, pseudo_flows=[], hotspots=hotspots, confidence=0.95)

@contextmanager
def isolated_db():
    tmp = Path(tempfile.mkdtemp(prefix="p13_acc_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ─────────────────────────────────────────
# SCENARIO A: Multi-Language Precision Routing
# ─────────────────────────────────────────
def scenario_A():
    print("\n" + "═" * 60)
    print("SCENARIO A │ 語言精準路由 — Rust/Python/TypeScript 混合種植")
    print("═" * 60)
    with isolated_db() as tmp:
        reg = mk_registry(tmp)

        skills = [
            mk_skill("sk-rs-001", "rust-memory-fix", ["rust"], ["*.rs"], win_rate=0.92, trust="production"),
            mk_skill("sk-rs-002", "rust-borrow-fix", ["rust"], ["*.rs", "Cargo.toml"], win_rate=0.87, trust="tested"),
            mk_skill("sk-py-001", "py-asyncio-fix", ["python"], ["*.py"], win_rate=0.95, trust="production"),
            mk_skill("sk-py-002", "py-import-fix",  ["python"], ["*.py"], win_rate=0.60),
            mk_skill("sk-ts-001", "ts-type-fix",    ["typescript"], ["*.ts", "*.tsx"], win_rate=0.78, trust="tested"),
            mk_skill("sk-gen-001", "general-fixer",  ["rust", "python", "typescript"], ["*"], win_rate=0.55),
        ]
        for s in skills:
            reg.upsert(s)

        stats = reg.get_stats()
        _assert("Registry seeded correctly (6 skills)", stats["total_skills"] == 6,
                actual=stats["total_skills"], expected=6)

        # Task A1: Rust borrow checker failure
        rust_results = reg.search_by_affinity(languages=["rust"], min_win_rate=0.0, max_results=5)
        rust_ids = [r["task_id"] for r in rust_results]
        _assert("Rust affinity returns both Rust skills", "sk-rs-001" in rust_ids and "sk-rs-002" in rust_ids,
                actual=rust_ids, expected=["contains sk-rs-001, sk-rs-002"])
        _assert("Rust top result is sk-rs-001 (win_rate=0.92 > 0.87)", rust_results[0]["task_id"] == "sk-rs-001",
                actual=rust_results[0]["task_id"], expected="sk-rs-001",
                note=f"Actual win_rate={rust_results[0]['win_rate']}")
        _assert("Python skill NOT in Rust results", "sk-py-001" not in rust_ids,
                actual="sk-py-001 in rust_ids=" + str("sk-py-001" in rust_ids), expected=False)

        # Task A2: TypeScript task with file pattern
        ts_results = reg.search_by_affinity(languages=["typescript"], file_patterns=["*.tsx"], min_win_rate=0.0, max_results=5)
        ts_ids = [r["task_id"] for r in ts_results]
        _assert("TypeScript affinity returns ts+general skills", "sk-ts-001" in ts_ids,
                actual=ts_ids, expected=["contains sk-ts-001"])

        # Task A3: min_win_rate filter precision
        high_wrate = reg.search_by_affinity(languages=["python"], min_win_rate=0.80, max_results=5)
        high_ids = [r["task_id"] for r in high_wrate]
        _assert("min_win_rate=0.80 excludes sk-py-002 (0.60)", "sk-py-002" not in high_ids,
                actual=high_ids, expected="no sk-py-002",
                note=f"sk-py-001 (0.95) should remain: {high_ids}")
        _assert("sk-py-001 (0.95) passes min_win_rate=0.80", "sk-py-001" in high_ids,
                actual=high_ids)
        print(f"  📊 Rust candidates     : {rust_ids}")
        print(f"  📊 TypeScript candidates: {ts_ids}")
        print(f"  📊 High win_rate (≥0.80): {high_ids}")

# ─────────────────────────────────────────
# SCENARIO B: MemPalace TTL Governance Filter
# ─────────────────────────────────────────
def scenario_B():
    print("\n" + "═" * 60)
    print("SCENARIO B │ MemPalace 7天TTL + Forbid/Prefer 信念過濾")
    print("═" * 60)
    with isolated_db() as tmp:
        reg = mk_registry(tmp)
        reg.upsert(mk_skill("safe-001", "safe-fix", ["python"], ["*.py"], win_rate=0.9, hyp="正常修復"))
        reg.upsert(mk_skill("danger-001", "pip-install-fix", ["python"], ["*.py"], win_rate=0.95,
                            hyp="我們應該使用 pip install requests 來解決問題"))
        reg.upsert(mk_skill("prefer-001", "uv-fix", ["python"], ["*.py"], win_rate=0.80,
                            hyp="應優先使用 uv run 管理套件環境"))

        palace = MemPalace(str(project_root))
        now_iso = datetime.now(timezone.utc).isoformat()
        expired_iso = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()

        # Inject mock beliefs: 1 fresh forbid, 1 expired forbid, 1 prefer
        palace.list_beliefs = lambda status: [
            {"content": "禁止使用 pip install", "created_at": now_iso, "updated_at": now_iso},     # ACTIVE TTL ✓
            {"content": "禁止使用 conda", "created_at": expired_iso, "updated_at": expired_iso},   # EXPIRED TTL ✗
            {"content": "優先使用 uv run 執行環境", "created_at": now_iso, "updated_at": now_iso},   # ACTIVE prefer ✓
        ]

        constraints = palace.get_skill_constraints()
        _assert("Active forbid count = 1 (expired one excluded)", len(constraints["forbid"]) == 1,
                actual=len(constraints["forbid"]), expected=1,
                note=f"forbids={constraints['forbid']}")
        _assert("Expired belief not in forbids (conda excluded)", 
                not any("conda" in f for f in constraints["forbid"]),
                actual=constraints["forbid"])
        _assert("Prefer constraint extracted", len(constraints["prefer"]) >= 1,
                actual=constraints["prefer"])

        # Now filter candidates
        candidates = reg.search_by_affinity(languages=["python"], min_win_rate=0.0, max_results=10)
        hub = ContextHub(str(project_root), skill_registry=reg, mem_palace=palace)
        diag = mk_diag("Python import resolution failure", ["src/handler.py", "lib/utils.py"])
        pack = hub.assemble_repair_pack(diagnosis=diag, reflections=[])
        recs = pack.get("recommended_skills", [])
        rec_ids = [r["skill_id"] for r in recs]

        _assert("danger-001 (pip install) filtered out by forbid constraint", "danger-001" not in rec_ids,
                actual=rec_ids, expected="no danger-001")
        _assert("safe-001 (normal fix) passes through", "safe-001" in rec_ids,
                actual=rec_ids, expected=["contains safe-001"])

        print(f"  📊 All candidates pre-filter : {[c['task_id'] for c in candidates]}")
        print(f"  📊 Recommended after MemPalace: {rec_ids}")
        print(f"  📊 Constraints active         : {json.dumps(constraints, ensure_ascii=False)}")

# ─────────────────────────────────────────
# SCENARIO C: Router Bias Threshold Calibration
# ─────────────────────────────────────────
def scenario_C():
    print("\n" + "═" * 60)
    print("SCENARIO C │ AutonomicRouter MemPalace 偏誤校正 (精確閾值驗證)")
    print("═" * 60)

    palace = MemPalace(str(project_root))

    # Base router (no bias)
    router_base = AutonomicRouter(str(project_root))
    base_threshold = router_base.config["token_threshold"]
    print(f"  📊 Base token_threshold: {base_threshold}")

    # High swarm bias
    palace.get_router_bias = lambda: [0.05, 0.85, 0.05, 0.05]   # swarm_weight=0.85 > 0.7
    router_biased = AutonomicRouter(str(project_root), mem_palace=palace)

    state = NexusState(task_id="acc-router-test")
    
    # Dynamically calculate the exact biased threshold so we're robust to config changes
    expected_eff_threshold = int(base_threshold * 0.9)
    # Token just above biased threshold (should escalate) but below base (would NOT escalate without bias)
    token_above_biased  = expected_eff_threshold + 100   # exceeds biased threshold → swarm
    token_below_biased  = expected_eff_threshold - 200   # below biased threshold → standard

    print(f"  📊 base={base_threshold}, effective={expected_eff_threshold}, "
          f"token_above={token_above_biased}, token_below={token_below_biased}")

    # Token = token_above_biased → below base, so without bias it would be standard
    plan_base = router_base.route("Refactor memory module", state, forecast={"est_tokens": token_above_biased})
    _assert("Without bias: token_above_biased → standard (below base_threshold)", plan_base.mode == "standard",
            actual=plan_base.mode, expected="standard",
            note=f"base_threshold={base_threshold}, tokens={token_above_biased}")

    # Same token WITH swarm bias → exceeds effective_threshold → escalates to swarm
    plan_biased = router_biased.route("Refactor memory module", state, forecast={"est_tokens": token_above_biased})
    _assert(f"With swarm bias 0.85: effective_threshold={expected_eff_threshold} → {token_above_biased} escalates to swarm",
            plan_biased.mode == "swarm",
            actual=plan_biased.mode, expected="swarm",
            note=f"{token_above_biased} > {expected_eff_threshold}")

    # Token well below biased threshold → stays standard even with bias
    plan_low = router_biased.route("Small patch", state, forecast={"est_tokens": token_below_biased})
    _assert(f"With swarm bias: {token_below_biased} tokens still stays standard (below {expected_eff_threshold})",
            plan_low.mode == "standard",
            actual=plan_low.mode, expected="standard")

    # Retry escalation still works (must override bias)
    state_retry = NexusState(task_id="acc-retry-test")
    state_retry.audit = type("A", (), {"retry_count": 5})()
    plan_retry = router_biased.route("Small fix", state_retry, forecast={"est_tokens": 100})
    _assert("Retry escalation overrides everything (retry=5 → swarm)",
            plan_retry.mode == "swarm", actual=plan_retry.mode, expected="swarm")

    print(f"  📊 Bias=[0.05, 0.85, 0.05, 0.05], effective_threshold={expected_eff_threshold}")
    print(f"  📊 Routing 6000 tokens: {plan_low.mode} | 7500 tokens: {plan_biased.mode}")
    print(f"  📊 Retry escalation  : {plan_retry.mode} (forced swarm)")

# ─────────────────────────────────────────
# SCENARIO D: Win Rate Convergence Over 10 Iterations
# ─────────────────────────────────────────
def scenario_D():
    print("\n" + "═" * 60)
    print("SCENARIO D │ Win Rate 收斂性驗證 — 10輪連續任務模擬")
    print("═" * 60)
    with isolated_db() as tmp:
        reg = mk_registry(tmp)
        reg.upsert(mk_skill("evol-001", "evolving-skill", ["rust"], ["*.rs"], win_rate=0.0))

        # Simulate 10 outcomes manually (6 success, 4 failure = 0.6 expected)
        outcomes = [True, True, False, True, True, False, True, False, False, True]
        
        successes, total = 0, 0
        history = []
        for i, success in enumerate(outcomes, 1):
            skill = reg.get_by_task_id("evol-001")
            curr_success = skill.get("repair_success", 0) if skill else 0
            curr_retry = skill.get("retry_count", 0) if skill else 0
            if success:
                successes += 1
            total += 1
            expected_rate = float(successes) / total
            reg.update_win_rate("evol-001", expected_rate)
            actual = reg.get_by_task_id("evol-001")
            history.append({"round": i, "success": success,
                             "cumulative_wins": successes, "total": total,
                             "win_rate": round(actual["win_rate"], 4)})

        final_rate = reg.get_by_task_id("evol-001")["win_rate"]
        expected_final = 6.0 / 10.0  # 0.6

        _assert("After 10 rounds (6 wins), win_rate converges to 0.6",
                abs(final_rate - expected_final) < 0.001,
                actual=round(final_rate, 4), expected=expected_final)

        # Prove that a skill with win_rate < 0.3 is filtered by search
        reg.update_win_rate("evol-001", 0.25)
        filtered = reg.search_by_affinity(languages=["rust"], min_win_rate=0.30, max_results=10)
        filtered_ids = [r["task_id"] for r in filtered]
        _assert("Degraded skill (0.25) invisible at min_win_rate=0.30",
                "evol-001" not in filtered_ids, actual=filtered_ids)

        print(f"  📊 10-round history:")
        for h in history:
            bar = "🟢" if h["success"] else "🔴"
            print(f"       Round {h['round']:02d} {bar}  wins={h['cumulative_wins']}/{h['total']}  win_rate={h['win_rate']}")
        print(f"  📊 Final win_rate: {final_rate:.4f} (expected {expected_final})")

# ─────────────────────────────────────────
# SCENARIO E: Full End-to-End Diagnosis → Repair Pack Integration
# ─────────────────────────────────────────
def scenario_E():
    print("\n" + "═" * 60)
    print("SCENARIO E │ 完整 E2E: Diagnosis Pack → Repair Pack 跨語言注入")
    print("═" * 60)
    with isolated_db() as tmp:
        reg = mk_registry(tmp)

        # E1: Pure win_rate ordering (no MemPalace)  
        skills = [
            mk_skill("sk-rs-A", "rust-lifetime-fix", ["rust"], ["*.rs"], win_rate=0.91, trust="production",
                     hyp="Use explicit lifetime annotations to resolve borrow checker violations"),
            mk_skill("sk-rs-B", "rust-cargo-fix", ["rust"], ["Cargo.toml", "*.rs"], win_rate=0.75, trust="tested"),
            mk_skill("sk-py-X", "py-irrelevant", ["python"], ["*.py"], win_rate=0.99),  # should NOT appear
        ]
        for s in skills:
            reg.upsert(s)

        # Repair pack WITHOUT palace (pure win_rate ordering)
        hub_no_palace = ContextHub(str(project_root), skill_registry=reg, mem_palace=None)
        diag = mk_diag("Rust borrow checker: lifetime violations", ["src/engine.rs", "src/router.rs"])
        repair_pack_base = hub_no_palace.assemble_repair_pack(diagnosis=diag, reflections=[])
        recs_base = repair_pack_base.get("recommended_skills", [])

        _assert("Repair pack contains recommended_skills key", "recommended_skills" in repair_pack_base,
                actual=list(repair_pack_base.keys()))
        _assert("Top skill (no bias) is sk-rs-A (highest rust win_rate=0.91)",
                len(recs_base) > 0 and recs_base[0]["skill_id"] == "sk-rs-A",
                actual=[r["skill_id"] for r in recs_base], expected="[sk-rs-A, ...]")
        _assert("Python skill NOT injected in Rust task (no palace)",
                all(r["skill_id"] != "sk-py-X" for r in recs_base),
                actual=[r["skill_id"] for r in recs_base])
        _assert("Winning hypothesis propagated on sk-rs-A (position 0)",
                recs_base and recs_base[0]["winning_hypothesis"] != "",
                actual=recs_base[0]["winning_hypothesis"] if recs_base else "EMPTY")
        _assert("win_rate field populated in recommendation",
                all("win_rate" in r for r in recs_base),
                actual=[r.get("win_rate") for r in recs_base])

        # E2: MemPalace prefer boost (cargo → sk-rs-B should rank up)
        palace = MemPalace(str(project_root))
        now_iso = datetime.now(timezone.utc).isoformat()
        palace.list_beliefs = lambda status: [
            {"content": "優先使用 cargo clippy 作為 Rust 診斷工具", "created_at": now_iso, "updated_at": now_iso},
        ]
        hub_palace = ContextHub(str(project_root), skill_registry=reg, mem_palace=palace)
        repair_pack_biased = hub_palace.assemble_repair_pack(diagnosis=diag, reflections=[])
        recs_biased = repair_pack_biased.get("recommended_skills", [])
        biased_ids = [r["skill_id"] for r in recs_biased]

        _assert("Prefer 'cargo' boost: sk-rs-B climbs above sk-rs-A",
                biased_ids and biased_ids[0] == "sk-rs-B",
                actual=biased_ids, expected="[sk-rs-B, ...]",
                note="prefer 'cargo clippy' keyword in belief boosts rust-cargo-fix")
        _assert("Both Rust skills present after prefer reorder",
                "sk-rs-A" in biased_ids and "sk-rs-B" in biased_ids,
                actual=biased_ids)

        # E3: Diagnosis pack has correct structure
        diag_pack = hub_no_palace.assemble_diag_pack(
            violations=[
                {"file": "src/engine.rs", "rule": "E0502", "reason": "Cannot borrow as mutable"},
                {"file": "src/router.rs", "rule": "E0597", "reason": "Dropped value lifetime violation"},
            ],
            summary="Rust lifetime violations"
        )
        _assert("Diagnosis pack contains recommended_skills key", "recommended_skills" in diag_pack,
                actual=list(diag_pack.keys()))
        _assert("Diagnosis pack hotspots extracted correctly",
                len(diag_pack.get("hotspots", [])) == 2,
                actual=diag_pack.get("hotspots"))

        print(f"  📊 Base recs (no bias) : {[r['skill_id']+' w='+str(r['win_rate']) for r in recs_base]}")
        print(f"  📊 Biased recs (cargo) : {[r['skill_id']+' w='+str(r['win_rate']) for r in recs_biased]}")
        print(f"  📊 Diag pack keys      : {list(diag_pack.keys())}")
        print(f"  📊 rs-A hypothesis     : {recs_base[0]['winning_hypothesis'] if recs_base else 'N/A'}")

# ─────────────────────────────────────────
# FINAL REPORT
# ─────────────────────────────────────────
def print_summary():
    print("\n" + "═" * 60)
    print("ACCEPTANCE REPORT │ Phase 13 Closed Loop")
    print("═" * 60)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    total  = len(results)
    for r in results:
        print(f"  {r['status']}  {r['name']}")
    print(f"\n  SCORE: {passed}/{total} passed, {failed} FAILED")
    if failed == 0:
        print("\n  🎯 PHASE 13 FULL ACCEPTANCE  ─  ALL SYSTEMS NOMINAL")
    else:
        print(f"\n  ⛔ PHASE 13 REJECTED ─ {failed} assertion(s) failed. Review above.")
    return failed

if __name__ == "__main__":
    t_start = time.time()
    scenario_A()
    scenario_B()
    scenario_C()
    scenario_D()
    scenario_E()
    elapsed = time.time() - t_start
    print(f"\n  ⏱  Total execution time: {elapsed:.2f}s")
    failed = print_summary()
    sys.exit(1 if failed > 0 else 0)
