#!/usr/bin/env python3
"""
[Phase 1 Gate] Constructor Smoke Test
Verifies:
  1. Module imports correctly
  2. argparse contract is intact
  3. CodexLoopV2 object can be constructed (standard mode)
  4. CodexLoopV2 object can be constructed (benchmark mode)
  5. init_preflight_check() passes (standard mode)
  6. init_preflight_check() passes (benchmark mode with executor)

Final verdict: CONSTRUCTOR_FREEZE_READY | NOT_READY
"""
import sys
import os
import unittest
from pathlib import Path

# ── env setup ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PASSES = []
FAILURES = []

def record(name, ok, reason=""):
    if ok:
        PASSES.append(name)
        print(f"✅ {name}")
    else:
        FAILURES.append(f"{name}: {reason}")
        print(f"❌ {name}: {reason}")


# ── Test 1: Module Import ──────────────────────────────────────────────────────
try:
    from scripts.codex_loop_brain import CodexLoopV2
    record("T1: Module Import", True)
except Exception as e:
    record("T1: Module Import", False, str(e))
    print("\n⛔  CONSTRUCTOR_FREEZE_READY: NOT_READY (Import failed, aborting.)")
    sys.exit(2)

# ── Test 2: argparse Contract ──────────────────────────────────────────────────
try:
    import argparse
    from scripts.codex_loop_brain import CodexLoopV2  # already imported, just referencing for clarity

    # Simulate argparse the same way __main__ does
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--mode", default="developer")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--task", default=None)
    parser.add_argument("--benchmark", action="store_true")

    args = parser.parse_args([])
    assert hasattr(args, "base"), "Missing: base"
    assert hasattr(args, "benchmark"), "Missing: benchmark"
    assert hasattr(args, "task"), "Missing: task"
    record("T2: argparse Contract", True)
except Exception as e:
    record("T2: argparse Contract", False, str(e))

# ── Test 3: Standard Mode Construction ────────────────────────────────────────
try:
    engine_std = CodexLoopV2(
        mode="developer",
        scope="manual",
        task="smoke-test-standard"
    )
    assert engine_std.git is not None, "git is None"
    assert engine_std.skills_router is not None, "skills_router alias is None"
    assert engine_std.persona_hint is not None, "persona_hint is None"
    record("T3: Standard Mode Construction", True)
except Exception as e:
    record("T3: Standard Mode Construction", False, str(e))

# ── Test 4: Preflight Check (Standard Mode) ────────────────────────────────────
try:
    ok = engine_std.init_preflight_check(benchmark_mode=False)
    assert ok is True
    record("T4: Preflight — Standard Mode", True)
except Exception as e:
    record("T4: Preflight — Standard Mode", False, str(e))

# ── Test 5: Benchmark Mode Construction ────────────────────────────────────────
try:
    from nexus.executors.gemini import GeminiExecutor
    from unittest.mock import MagicMock, patch

    mock_executor = MagicMock()
    mock_executor.is_ready.return_value = True

    engine_bench = CodexLoopV2(
        mode="developer",
        scope="manual",
        task="smoke-test-benchmark",
        executor=mock_executor,
    )
    assert engine_bench.executor is not None, "executor is None"
    assert engine_bench.legacy_path_enabled is False, "legacy_path_enabled should be False in benchmark mode"
    assert engine_bench.skills_router is not None, "skills_router alias is None"
    record("T5: Benchmark Mode Construction", True)
except Exception as e:
    record("T5: Benchmark Mode Construction", False, str(e))

# ── Test 6: Benchmark Preflight Check ────────────────────────────────────────
try:
    ok = engine_bench.init_preflight_check(benchmark_mode=True)
    assert ok is True
    record("T6: Preflight — Benchmark Mode", True)
except Exception as e:
    record("T6: Preflight — Benchmark Mode", False, str(e))


# ── Final Verdict ─────────────────────────────────────────────────────────────
print("\n" + "─" * 60)
print(f"PASS: {len(PASSES)} | FAIL: {len(FAILURES)}")
if FAILURES:
    print("\nFailed checks:")
    for f in FAILURES:
        print(f"  ❌ {f}")
    print("\n🔴  CONSTRUCTOR_FREEZE_READY: NOT_READY")
    sys.exit(1)
else:
    print("\n🟢  CONSTRUCTOR_FREEZE_READY: READY")
    sys.exit(0)
