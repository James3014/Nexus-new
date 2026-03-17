#!/usr/bin/env python3
"""
[Phase 2 Gate] Benchmark Entry Smoke Test
Verifies:
  1. canonical nexus_benchmark.sh exists and is executable
  2. CLI parser is intact (--task required, --mode validated)
  3. GitManager initializes with valid project_root
  4. Benchmark pre-review path is reachable (init_preflight_check passes)
  5. No crash in DI / import / argparse / service wiring stage

Final verdict: BENCHMARK_ENTRYPOINT_READY | NOT_READY
"""
import sys
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

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


def main():
    # ── T1: Canonical launcher exists ─────────────────────────────────────────────
    launcher = REPO_ROOT / "nexus_benchmark.sh"
    try:
        assert launcher.exists(), "nexus_benchmark.sh not found"
        assert os.access(launcher, os.X_OK), "nexus_benchmark.sh not executable"
        record("T1: Canonical Launcher Exists & Executable", True)
    except AssertionError as e:
        record("T1: Canonical Launcher Exists & Executable", False, str(e))

    # ── T2: CLI contract — missing --task fails with CLI_CONTRACT_ERROR ────────────
    try:
        result = subprocess.run(
            ["bash", str(launcher)],
            capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "CLI_CONTRACT_ERROR" in result.stderr, "Missing CLI_CONTRACT_ERROR in stderr"
        record("T2: CLI Contract — Missing --task Returns CLI_CONTRACT_ERROR", True)
    except Exception as e:
        record("T2: CLI Contract — Missing --task Returns CLI_CONTRACT_ERROR", False, str(e))

    # ── T3: CLI contract — invalid --mode fails ────────────────────────────────────
    try:
        result = subprocess.run(
            ["bash", str(launcher), "--task", "test", "--mode", "invalid-mode"],
            capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 2, f"Expected exit 2 for invalid mode, got {result.returncode}"
        assert "CLI_CONTRACT_ERROR" in result.stderr
        record("T3: CLI Contract — Invalid --mode Returns CLI_CONTRACT_ERROR", True)
    except Exception as e:
        record("T3: CLI Contract — Invalid --mode Returns CLI_CONTRACT_ERROR", False, str(e))

    # ── T4: GitManager service wiring ─────────────────────────────────────────────
    try:
        from nexus.services.git import GitManager
        git = GitManager(project_root=str(REPO_ROOT))
        assert git is not None, "GitManager is None"
        assert getattr(git, "project_root", None) is not None, "git.project_root is None"
        record("T4: GitManager Service Wiring", True)
    except Exception as e:
        record("T4: GitManager Service Wiring", False, str(e))

    # ── T5: Benchmark pre-review path reachable ────────────────────────────────────
    try:
        from nexus.services.reviewer import CodexLoopV2

        mock_executor = MagicMock()
        engine = CodexLoopV2(
            mode="developer",
            scope="manual",
            task="entrypoint-smoke-test",
            executor=mock_executor,
        )
        ok = engine.init_preflight_check(benchmark_mode=True)
        assert ok is True
        record("T5: Benchmark Pre-review Path Reachable (Preflight Passes)", True)
    except Exception as e:
        record("T5: Benchmark Pre-review Path Reachable (Preflight Passes)", False, str(e))


    # ── Final Verdict ─────────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print(f"PASS: {len(PASSES)} | FAIL: {len(FAILURES)}")
    if FAILURES:
        print("\nFailed checks:")
        for f in FAILURES:
            print(f"  ❌ {f}")
        print("\n🔴  BENCHMARK_ENTRYPOINT_READY: NOT_READY")
        sys.exit(1)
    else:
        print("\n🟢  BENCHMARK_ENTRYPOINT_READY: READY")
        sys.exit(0)

if __name__ == "__main__":
    main()
