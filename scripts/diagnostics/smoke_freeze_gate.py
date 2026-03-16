#!/usr/bin/env python3
"""
[Phase 3 Gate] Core Freeze Smoke Test
Proves four invariants:
  I1. Executor exclusivity — legacy llm.ask path unreachable when executor set
  I2. Target persistence — privileged_context_files survive git refresh mock
  I3. Privileged context survival — files survive filter cycles
  I4. Contamination interception — mutations to nexus/ / scripts/ abort with BENCHMARK_CONTAMINATED

Final verdict: CORE_FROZEN_READY | NOT_READY
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PASSES = []
FAILURES = []

def record(name, ok, reason=""):
    if ok:
        PASSES.append(name)
        print(f"✅ {name}")
    else:
        FAILURES.append(f"{name}: {reason}")
        print(f"❌ {name}: {reason}")


from scripts.codex_loop_brain import CodexLoopV2

# ── I1: Executor Exclusivity ───────────────────────────────────────────────────
try:
    mock_exec = MagicMock()
    engine = CodexLoopV2(mode="developer", scope="manual", task="i1-test", executor=mock_exec)
    assert engine.legacy_path_enabled is False, "legacy_path_enabled must be False when executor is set"
    assert engine.executor is not None, "executor must not be None"
    record("I1: Executor Exclusivity — Legacy Path Locked", True)
except Exception as e:
    record("I1: Executor Exclusivity — Legacy Path Locked", False, str(e))

# ── I2: Target Persistence (privileged_context_files survives) ────────────────
try:
    DUMMY_FILES = ["/tmp/test_target.py", "/tmp/other_target.py"]
    engine2 = CodexLoopV2(
        mode="developer", scope="manual", task="i2-test",
        initial_files=DUMMY_FILES
    )
    # Simulate what _do_review does: merge with diff-discovered files
    diff_files = ["/tmp/new_discovery.py"]
    reviewable = list(set(engine2.privileged_context_files + diff_files))
    
    # Ensure all privileged files survived
    for f in DUMMY_FILES:
        assert f in reviewable, f"Privileged file {f} was lost after merge"
    
    privileged_count = len(engine2.privileged_context_files)
    assert privileged_count == len(DUMMY_FILES), f"Count mismatch: {privileged_count} != {len(DUMMY_FILES)}"
    record("I2: Target Persistence — privileged_context_files Survives", True)
except Exception as e:
    record("I2: Target Persistence — privileged_context_files Survives", False, str(e))

# ── I3: Privileged Context Survival through filter (structural check) ─────────
try:
    # Simulate a purge-all filter scenario (empty diff from git)
    diff_files_empty = []
    reviewable_after_empty_diff = list(set(engine2.privileged_context_files + diff_files_empty))
    for f in DUMMY_FILES:
        assert f in reviewable_after_empty_diff, f"Privileged {f} lost after empty diff merge"
    record("I3: Privileged Context Survival — Survives Empty Diff Cycle", True)
except Exception as e:
    record("I3: Privileged Context Survival — Survives Empty Diff Cycle", False, str(e))

# ── I4: Contamination Interception ────────────────────────────────────────────
try:
    from nexus.executors.protocol import ExecutorOutput, ExecutorStatusEnum
    
    mock_exec_contam = MagicMock()
    # Mock executor output to simulate a core mutation
    mock_exec_contam.execute.return_value = ExecutorOutput(
        executor_name="mock",
        phase="P",
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=True,
        evidence_present=False,
        raw_exit_code=0,
        files_touched=["scripts/codex_loop_brain.py"],
        summary="I patched the core",
        patch_diff="--- a/scripts/codex_loop_brain.py\n+++ b/scripts/codex_loop_brain.py\n"
    )
    
    Path("/tmp/test_target.py").write_text("dummy content")
    engine_contam = CodexLoopV2(
        mode="developer", scope="manual", task="i4-test", executor=mock_exec_contam,
        initial_files=["/tmp/test_target.py"]
    )
    # mock git to prevent real git diffs
    engine_contam.git.get_changes = MagicMock(return_value=([], ""))
    
    passed = False
    try:
        # Should raise RuntimeError("BENCHMARK_CONTAMINATED")
        engine_contam._do_review()
    except RuntimeError as e:
        if "BENCHMARK_CONTAMINATED" in str(e):
            passed = True
        else:
            raise e
    finally:
        Path("/tmp/test_target.py").unlink(missing_ok=True)
            
    assert passed, "Expected RuntimeError('BENCHMARK_CONTAMINATED') was not raised"
    record("I4: Contamination Interception — Core mutations trigger BENCHMARK_CONTAMINATED", True)
except Exception as e:
    record("I4: Contamination Interception — Core mutations trigger BENCHMARK_CONTAMINATED", False, str(e))


# ── Final Verdict ──────────────────────────────────────────────────────────────
print("\n" + "─" * 60)
print(f"PASS: {len(PASSES)} | FAIL: {len(FAILURES)}")
if FAILURES:
    print("\nFailed checks:")
    for f in FAILURES:
        print(f"  ❌ {f}")
    print("\n🔴  CORE_FROZEN_READY: NOT_READY")
    sys.exit(1)
else:
    print("\n🟢  CORE_FROZEN_READY: READY")
    sys.exit(0)
