"""Portability contract for restored bench entrypoints (Issue #352)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH_DIR = REPO_ROOT / "scripts" / "bench"

RESTORED_IDS = [
    "concurrency_001",
    "concurrency_002",
    "concurrency_003",
    "concurrency_004",
    "concurrency_005",
    "concurrency_006",
    "concurrency_007",
    "concurrency_008",
    "evidence_gap_001",
    "action_protocol_001",
    "verifier_gap_001",
    "anchored_edit_gap_001",
    "anchored_edit_gap_002",
    "anchored_edit_gap_003",
    "anchored_edit_gap_004",
]

ARTIFACTS_DIR = (
    REPO_ROOT
    / "artifacts"
    / "runtime"
    / "av_executable_benchmark_substrate_v0"
    / "execution_results"
)


def _artifact_files() -> set:
    if not ARTIFACTS_DIR.exists():
        return set()
    return {str(p) for p in ARTIFACTS_DIR.rglob("*")}


def test_portable_repo_root_resolves_to_checkout():
    spec = importlib.util.spec_from_file_location("bench_repo_root", BENCH_DIR / "_repo_root.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    assert module.REPO_ROOT == REPO_ROOT
    assert (module.REPO_ROOT / "scripts" / "bench" / "_repo_root.py").is_file()


@pytest.mark.parametrize("tid", RESTORED_IDS)
def test_restored_script_dry_run_zero_writes(tmp_path, tid):
    script = BENCH_DIR / f"run_{tid}_regression.py"
    explicit_output = tmp_path / f"{tid}.json"
    before = _artifact_files()

    result = subprocess.run(
        [sys.executable, str(script), "--dry-run", "--output", str(explicit_output)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, f"dry-run failed for {tid}: {result.stderr}"
    output = json.loads(result.stdout)
    assert output["task_id"] == tid
    assert output["verifier_status"] == "DRY_RUN"
    assert output["internal_only"] is True
    assert not explicit_output.exists(), "dry-run must not write --output file"
    assert _artifact_files() == before, "dry-run must not write default artifact path"


@pytest.mark.parametrize("tid", RESTORED_IDS + ["rebuild_av_substrate"])
def test_no_machine_specific_root_literal(tid):
    path = BENCH_DIR / (
        f"run_{tid}_regression.py" if tid != "rebuild_av_substrate" else "rebuild_av_substrate.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "/Users/jameschen" not in text
    assert "from _repo_root import REPO_ROOT" in text


def test_generator_template_uses_portable_root():
    text = (BENCH_DIR / "rebuild_av_substrate.py").read_text(encoding="utf-8")
    assert "from _repo_root import REPO_ROOT" in text
    assert "/Users/jameschen" not in text
