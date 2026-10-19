"""Regression tests for #2685: three EvidenceVerifier/Replay pass-through holes.

1. An honest failing receipt (``exit_code: 1`` reproduced) must never pass or reach HIGH.
2. Base test ids that vanish on the candidate while the claim says tests pass: at most
   MEDIUM, with a finding naming the removed ids; collection impossible -> UNKNOWN, never HIGH.
3. Nothing replayable -> ``passed: False`` / UNVERIFIED, never success.

The nine refusals from the L1 diagnosis (shell injection, --basetemp, ../ escape, forged
stdout hash, false exit 0, deleted test file named, non-verifier command, broken code,
fabricated receipt) must keep holding; they are asserted here against real subprocesses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from nexus.delivery.anti_drift import AntiDrift
from nexus.delivery.evidence_verifier import EvidenceVerifier
from nexus.delivery.replay_runner import ReplayRunner

ROOT = Path(__file__).resolve().parents[2]
OK_CMD = "python -m pytest -q tests/test_ok.py -p no:cacheprovider"
ALL_CMD = "python -m pytest -q tests -p no:cacheprovider"


@pytest.fixture(autouse=True)
def _python_on_path(monkeypatch):
    # Replayed commands resolve `python` from PATH: make it the interpreter running the tests.
    monkeypatch.setenv(
        "PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _project(tmp_path: Path, *, manifest: bool = False) -> Path:
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "tests/test_ok.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    (root / "tests/test_edge.py").write_text(
        "from calc import add\n\ndef test_neg():\n    assert add(-1, 1) == 0\n"
    )
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    if manifest:
        AntiDrift.generate_manifest(root, root / "nexus/config/governance_manifest.json")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _bundle(test_artifacts: list) -> dict:
    return {"version": "1.1.0", "code_artifacts": ["calc.py"], "test_artifacts": test_artifacts}


def _break_code(root: Path) -> None:
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n")


def _touch_code(root: Path) -> None:
    (root / "calc.py").write_text("def add(a, b):\n    return a + b  # touched\n")


# --- hole 1: an honest failing receipt -------------------------------------------------
def test_replay_honest_failing_receipt_is_not_passed(tmp_path):
    root = _project(tmp_path)
    _break_code(root)
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [{"command": OK_CMD, "exit_code": 1}]
    })
    item = report["replay_results"][0]
    assert item["actual_exit_code"] == 1 and item["match_rc"] is True
    assert item["exit_ok"] is False
    assert item["passed"] is False
    assert report["passed"] is False
    assert report["status"] == "FAILED"


def test_replay_recorded_nonzero_for_missing_test_file_is_not_passed(tmp_path):
    root = _project(tmp_path)
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [{"command": "python -m pytest -q tests/test_nope.py", "exit_code": 4}]
    })
    assert report["passed"] is False


def test_verifier_honest_failing_receipt_is_never_high(tmp_path):
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    res = EvidenceVerifier(root).verify(_bundle([{"command": OK_CMD, "exit_code": 1}]))
    assert res["overall_trust"] != "HIGH"
    assert res["overall_trust"] == "LOW"
    assert res["status"] == "REJECTED"


def test_verifier_all_executed_requires_each_command_passed(tmp_path):
    root = _project(tmp_path)
    _break_code(root)
    report = EvidenceVerifier(root)._verify_test_commands([{"command": OK_CMD, "exit_code": 1}])
    assert report["executed"][0]["exit_code"] == 1
    assert report["executed"][0]["passed"] is False
    assert report["all_executed"] is False


def test_verifier_failing_test_rerun_is_not_high_even_if_replay_passed(tmp_path):
    # Defence in depth: even if the replay stage were bypassed, the verifier's own re-run
    # of a failing test must keep trust below HIGH.
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    fake_replay = {"status": "COMPLETED", "passed": True, "replay_count": 1}
    with patch.object(ReplayRunner, "run_replay", return_value=fake_replay):
        res = EvidenceVerifier(root).verify(_bundle([{"command": OK_CMD, "exit_code": 1}]))
    assert res["overall_trust"] != "HIGH"
    assert "test_commands_failed" in res["reject_reasons"]


def test_declared_nonzero_exit_matches_but_is_capped_below_high(tmp_path):
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    spec = {"command": OK_CMD, "expected_exit_code": 1}
    report = ReplayRunner(root).run_replay({"test_artifacts": [spec]})
    assert report["passed"] is True
    assert report["replay_results"][0]["declared_expected_exit_code"] == 1
    res = EvidenceVerifier(root).verify(_bundle([spec]))
    assert res["overall_trust"] == "MEDIUM"
    assert "declared_nonzero_exit" in res["reject_reasons"]


@pytest.mark.parametrize("declared", [0, True, "1", 1.0])
def test_invalid_declared_exit_code_is_rejected_not_executed(tmp_path, declared):
    root = _project(tmp_path)
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [{"command": OK_CMD, "expected_exit_code": declared}]
    })
    assert report["status"] == "REJECTED"
    assert report["passed"] is False
    assert report["replay_count"] == 0


def test_honest_passing_receipt_is_still_high(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    res = EvidenceVerifier(root).verify(_bundle([{"command": OK_CMD, "exit_code": 0}]))
    assert res["overall_trust"] == "HIGH", res
    assert res["test_set_comparison"]["status"] == "OK"


# --- hole 2: delete-and-replace ----------------------------------------------------------
def test_delete_and_replace_tests_is_at_most_medium_with_removed_ids(tmp_path):
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    (root / "tests/test_ok.py").unlink()
    (root / "tests/test_edge.py").unlink()
    (root / "tests/test_trivial.py").write_text("def test_nothing():\n    assert True\n")
    res = EvidenceVerifier(root).verify(_bundle([{"command": ALL_CMD, "exit_code": 0}]))
    assert res["overall_trust"] != "HIGH"
    assert res["overall_trust"] == "MEDIUM"
    assert "tests_removed" in res["reject_reasons"]
    comparison = res["test_set_comparison"]
    assert comparison["status"] == "TESTS_REMOVED"
    assert comparison["removed_ids"] == [
        "tests/test_edge.py::test_neg",
        "tests/test_ok.py::test_add",
    ]
    assert "tests/test_ok.py::test_add" in comparison["finding"]


def test_removing_one_test_function_is_detected(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    (root / "tests/test_edge.py").write_text("def test_other():\n    assert True\n")
    res = EvidenceVerifier(root).verify(_bundle([{"command": ALL_CMD, "exit_code": 0}]))
    assert res["overall_trust"] == "MEDIUM"
    assert res["test_set_comparison"]["removed_ids"] == ["tests/test_edge.py::test_neg"]


def test_adding_tests_is_not_a_removal(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    (root / "tests/test_new.py").write_text("def test_new():\n    assert True\n")
    res = EvidenceVerifier(root).verify(_bundle([{"command": ALL_CMD, "exit_code": 0}]))
    assert res["overall_trust"] == "HIGH", res
    assert res["test_set_comparison"]["status"] == "OK"
    assert res["test_set_comparison"]["removed_count"] == 0


def test_comparison_does_not_touch_the_repository(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout
    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=root, capture_output=True, text=True
    ).stdout
    EvidenceVerifier(root).verify(_bundle([{"command": ALL_CMD, "exit_code": 0}]))
    assert (
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
        ).stdout
        == before
    )
    assert (
        subprocess.run(["git", "worktree", "list"], cwd=root, capture_output=True, text=True).stdout
        == worktrees
    )


def test_collection_impossible_is_unknown_never_high(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    verifier = EvidenceVerifier(root, base_ref="no-such-ref")
    res = verifier.verify(_bundle([{"command": OK_CMD, "exit_code": 0}]))
    assert res["test_set_comparison"]["status"] == "UNKNOWN"
    assert "test_set_comparison_unknown" in res["reject_reasons"]
    assert res["overall_trust"] == "MEDIUM"


def test_collection_runs_argv_only_with_timeout(tmp_path, monkeypatch):
    import nexus.delivery.evidence_verifier as ev

    root = _project(tmp_path)
    seen: list = []
    real_run = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append((argv, kwargs))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(ev.subprocess, "run", spy)
    ev.collect_test_ids(("python", "-m", "pytest"), ["tests"], root)
    argv, kwargs = seen[-1]
    assert isinstance(argv, list) and "--collect-only" in argv
    assert not kwargs.get("shell")
    assert kwargs["timeout"] == ev.TEST_SET_COLLECT_TIMEOUT_SECONDS


# --- hole 3: nothing to replay -----------------------------------------------------------
@pytest.mark.parametrize("artifacts", [[], ["ran pytest, all green", "claims_count=7"]])
def test_replay_with_nothing_replayable_is_not_passed(tmp_path, artifacts):
    report = ReplayRunner(tmp_path).run_replay({"test_artifacts": artifacts})
    assert report["passed"] is False
    assert report["verdict"] == "UNVERIFIED"
    assert report["replay_count"] == 0


@pytest.mark.parametrize("artifacts", [[], ["all tests pass, trust me"]])
def test_verifier_with_nothing_replayable_is_unverified_not_success(tmp_path, artifacts):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    res = EvidenceVerifier(root).verify(_bundle(artifacts))
    assert res["verdict"] == "UNVERIFIED"
    assert res["passed"] is False
    assert res["overall_trust"] not in {"HIGH", "MEDIUM"}
    # #2624: still an advisory coverage gap, not a replay failure.
    assert res["status"] == "UNCOVERED"


def test_delivery_gate_cli_notes_only_stays_unverified(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"evidence_bundle": {"test_artifacts": ["claims_count=7"]}}))
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ops/replay_runner.py"), str(evidence)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )
    data = json.loads(proc.stdout)
    assert data["status"] == "UNVERIFIED"
    assert data["reason"] == "NO_REPLAYABLE_COMMANDS"


# --- the nine L1 refusals still hold -----------------------------------------------------
@pytest.mark.parametrize(
    ("name", "spec"),
    [
        ("shell_injection", {"command": "python -m pytest -q; touch PWNED", "exit_code": 0}),
        ("basetemp", {"command": "python -m pytest --basetemp=/tmp/zz tests", "exit_code": 0}),
        ("path_escape", {"command": "python -m pytest ../../etc", "exit_code": 0}),
        ("not_a_verifier", {"command": "rm -rf tests", "exit_code": 0}),
    ],
)
def test_l1_refusals_unsafe_commands_are_rejected_unexecuted(tmp_path, name, spec):
    root = _project(tmp_path)
    report = ReplayRunner(root).run_replay({"test_artifacts": [spec]})
    assert report["status"] == "REJECTED", name
    assert report["passed"] is False
    assert report["replay_count"] == 0
    assert (root / "tests").exists() and not (root / "PWNED").exists()


def test_l1_refusal_forged_stdout_hash(tmp_path):
    root = _project(tmp_path)
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [{"command": OK_CMD, "exit_code": 0, "output_hash": "0" * 64}]
    })
    assert report["status"] == "FAILED" and report["passed"] is False


def test_l1_refusal_false_exit_zero_on_broken_code(tmp_path):
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [{"command": OK_CMD, "exit_code": 0}]
    })
    assert report["status"] == "FAILED" and report["passed"] is False
    res = EvidenceVerifier(root).verify(_bundle([{"command": OK_CMD, "exit_code": 0}]))
    assert res["overall_trust"] == "LOW" and res["reason"] == "replay_failed"


def test_l1_refusal_recorded_exit_mismatch(tmp_path):
    # Receipt says exit 1 but the test passes now: receipt and reality disagree.
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    res = EvidenceVerifier(root).verify(_bundle([{"command": OK_CMD, "exit_code": 1}]))
    assert res["overall_trust"] == "LOW" and res["reason"] == "replay_failed"


def test_l1_refusal_deleted_test_file_named(tmp_path):
    root = _project(tmp_path)
    (root / "tests/test_ok.py").unlink()
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [{"command": OK_CMD, "exit_code": 0}]
    })
    assert report["status"] == "FAILED" and report["passed"] is False
