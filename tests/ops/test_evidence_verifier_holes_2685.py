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


@pytest.mark.parametrize("declared", [1, 4])
def test_declared_expected_exit_code_never_passes(tmp_path, declared):
    # The agent writes the receipt: an `expected_exit_code` key must not turn a failing
    # command into a pass (review B1).  It is ignored; the recorded default is exit 0.
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    cmd = OK_CMD if declared == 1 else "python -m pytest -q -p no:cacheprovider tests/test_nope.py"
    spec = {"command": cmd, "expected_exit_code": declared}
    report = ReplayRunner(root).run_replay({"test_artifacts": [spec]})
    assert report["passed"] is False
    assert report["replay_results"][0]["actual_exit_code"] == declared
    res = EvidenceVerifier(root).verify(_bundle([spec]))
    assert res["overall_trust"] == "LOW"


def _cli_verify(tmp_path: Path, test_artifacts: list) -> tuple[int, dict]:
    """Run scripts/ops/evidence_verifier.py (the `nexus delivery-gate` verifier) from the repo root."""
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps({
            "final_response": "The task is ready for review.",
            "evidence_bundle": {"code_artifacts": ["app.py"], "test_artifacts": test_artifacts},
        })
    )
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ops/evidence_verifier.py"), str(evidence)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=180,
        env=env,
    )
    return proc.returncode, json.loads(proc.stdout[proc.stdout.index("{\n") :])


def test_delivery_gate_cli_declared_nonzero_exit_is_not_verified(tmp_path):
    code, data = _cli_verify(
        tmp_path,
        [
            {
                "command": "python3 -m pytest -q -p no:cacheprovider tests/does_not_exist_2685.py",
                "expected_exit_code": 4,
            }
        ],
    )
    assert data["status"] != "VERIFIED"
    assert data["overall_trust"] != "HIGH"
    assert data["replay"]["status"] == "FAIL"
    assert code != 0


def test_delivery_gate_cli_recorded_nonzero_exit_is_not_verified(tmp_path):
    code, data = _cli_verify(
        tmp_path,
        [
            {
                "command": "python3 -m pytest -q -p no:cacheprovider tests/does_not_exist_2685.py",
                "exit_code": 4,
            }
        ],
    )
    assert data["status"] == "REJECTED"
    assert code != 0


@pytest.mark.parametrize("flag", ["--version", "--collect-only", "--co"])
def test_delivery_gate_cli_non_test_running_claim_is_not_verified(tmp_path, flag):
    # The CLI replays from the repo root.  Collection flags get one small, hermetic target
    # so the replay does not depend on whether the whole suite collects on this host.
    target = "" if flag == "--version" else " tests/ops/test_governance_manifest_sync.py"
    code, data = _cli_verify(
        tmp_path,
        [{"command": f"python3 -m pytest -p no:cacheprovider {flag}{target}", "exit_code": 0}],
    )
    # The promise: a claim that runs no tests is never VERIFIED / HIGH.
    assert data["status"] != "VERIFIED"
    assert data["overall_trust"] != "HIGH"
    assert code != 0
    if flag == "--version":
        assert data["status"] == "UNVERIFIED"
        assert data["reason"] == "NO_TEST_RUNNING_COMMAND"
        assert data["replay"]["test_running_count"] == 0
    else:
        # A collection error on some host makes the replay fail (REJECTED): stricter, still
        # not a pass.  With the hermetic target it is normally UNVERIFIED.
        assert data["status"] in {"UNVERIFIED", "REJECTED"}
        if data["status"] == "UNVERIFIED":
            assert data["reason"] == "NO_TEST_RUNNING_COMMAND"


@pytest.mark.parametrize("flag", ["--version", "--co", "--collect-only"])
def test_verifier_non_test_running_claim_is_capped_at_medium(tmp_path, flag):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    res = EvidenceVerifier(root).verify(
        _bundle([{"command": f"python -m pytest {flag}", "exit_code": 0}])
    )
    assert res["overall_trust"] == "MEDIUM"
    assert "no_test_running_command" in res["reject_reasons"]


def test_replay_counts_only_test_running_commands(tmp_path):
    root = _project(tmp_path)
    report = ReplayRunner(root).run_replay({
        "test_artifacts": [
            {"command": "python -m pytest --version", "exit_code": 0},
            {"command": OK_CMD, "exit_code": 0},
        ]
    })
    assert report["passed"] is True
    assert [r["runs_tests"] for r in report["replay_results"]] == [False, True]
    assert report["test_running_count"] == 1


@pytest.mark.parametrize(
    ("args", "flag"),
    [
        ("-k add tests", "-k"),
        ("-qk add tests", "-k"),
        ("-m 'not slow' tests", "-m"),
        ("--deselect tests/test_edge.py::test_neg tests", "--deselect"),
        ("--deselect=tests/test_edge.py::test_neg tests", "--deselect"),
        ("--lf tests", "--lf"),
        ("--ff tests", "--ff"),
        ("--sw tests", "--sw"),
    ],
)
def test_selection_flags_cap_at_medium_with_finding(tmp_path, args, flag):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    # --lf/--ff/--sw need the cache plugin, so no `-p no:cacheprovider` here.
    cmd = f"python -m pytest -q {args}"
    res = EvidenceVerifier(root).verify(_bundle([{"command": cmd, "exit_code": 0}]))
    assert res["overall_trust"] == "MEDIUM", res
    assert "test_selection_narrowed" in res["reject_reasons"]
    assert flag in res["test_selection"]["flags"]
    assert flag in res["test_selection"]["finding"]


def test_non_selection_flags_do_not_cap(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    cmd = "python -m pytest -q -x -p no:cacheprovider --tb short -rA tests"
    res = EvidenceVerifier(root).verify(_bundle([{"command": cmd, "exit_code": 0}]))
    assert res["overall_trust"] == "HIGH", res
    assert res["test_selection"]["flags"] == []


def test_narrow_claim_after_deleting_tests_is_flagged(tmp_path):
    # The claim names only a new file, so the test-set comparison sees nothing removed;
    # the deleted test files are flagged regardless of what the claim names.
    root = _project(tmp_path, manifest=True)
    _break_code(root)
    (root / "tests/test_ok.py").unlink()
    (root / "tests/test_edge.py").unlink()
    (root / "tests/test_trivial.py").write_text("def test_nothing():\n    assert True\n")
    cmd = "python -m pytest -q -p no:cacheprovider tests/test_trivial.py"
    res = EvidenceVerifier(root).verify(_bundle([{"command": cmd, "exit_code": 0}]))
    assert res["overall_trust"] == "MEDIUM", res
    assert "test_files_deleted" in res["reject_reasons"]
    assert res["deleted_test_files"]["paths"] == ["tests/test_edge.py", "tests/test_ok.py"]
    assert "tests/test_ok.py" in res["deleted_test_files"]["finding"]


def test_renamed_away_test_file_is_flagged(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    (root / "tests/test_edge.py").rename(root / "edge_helpers.py")
    cmd = "python -m pytest -q -p no:cacheprovider tests/test_ok.py"
    res = EvidenceVerifier(root).verify(_bundle([{"command": cmd, "exit_code": 0}]))
    assert res["overall_trust"] == "MEDIUM"
    assert res["deleted_test_files"]["paths"] == ["tests/test_edge.py"]


@pytest.mark.parametrize("ref", ["--output=/tmp/x", "-p", ""])
def test_option_like_base_ref_fails_closed(tmp_path, ref, monkeypatch):
    import nexus.delivery.evidence_verifier as ev

    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    seen: list = []
    real_run = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append(list(argv))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(ev.subprocess, "run", spy)
    res = EvidenceVerifier(root, base_ref=ref).verify(
        _bundle([{"command": OK_CMD, "exit_code": 0}])
    )
    assert res["overall_trust"] == "MEDIUM"
    assert res["test_set_comparison"] == {"status": "UNKNOWN", "reason": "invalid_base_ref"}
    assert res["deleted_test_files"]["status"] == "UNKNOWN"
    assert not any(ref and ref in argv for argv in seen if argv and argv[0] == "git")


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
    real_reap = ev.run_reaping_process_group

    def spy_reap(argv, *args, **kwargs):
        # Collection runs through the process-group reaping runner (#3052).
        seen.append((argv, kwargs))
        return real_reap(argv, *args, **kwargs)

    monkeypatch.setattr(ev, "run_reaping_process_group", spy_reap)
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


@pytest.mark.parametrize(
    "args",
    [
        ["-V"],
        ["-qV"],
        ["-h"],
        ["--help"],
        ["--fixtures"],
        ["--markers"],
        ["--setup-plan", "tests"],
        ["--version"],
        ["--co"],
        ["--collect-only=yes"],
    ],
)
def test_non_running_pytest_options_are_detected(args):
    # Review r2 (Gemini, Low): short and clustered forms run no tests either.
    from nexus.delivery.evidence_verifier import _pytest_targets
    from nexus.delivery.replay_runner import command_runs_tests

    assert command_runs_tests(["python", "-m", "pytest", *args]) is False
    assert command_runs_tests(["uv", "run", "pytest", *args]) is False
    assert _pytest_targets(args) is None


@pytest.mark.parametrize("args", [["-q", "tests"], ["-kV", "tests"], ["-x", "-rA", "tests"]])
def test_running_pytest_options_are_not_misdetected(args):
    # "-kV" is "-k V" (a keyword expression), not -V.
    from nexus.delivery.replay_runner import command_runs_tests

    assert command_runs_tests(["python", "-m", "pytest", *args]) is True


@pytest.mark.parametrize("flag", ["-V", "-qV"])
def test_delivery_gate_cli_short_version_claim_is_not_verified(tmp_path, flag):
    code, data = _cli_verify(tmp_path, [{"command": f"python3 -m pytest {flag}", "exit_code": 0}])
    assert data["status"] != "VERIFIED"
    assert data["overall_trust"] != "HIGH"
    assert code != 0


def test_verifier_short_version_claim_is_never_high(tmp_path):
    root = _project(tmp_path, manifest=True)
    _touch_code(root)
    res = EvidenceVerifier(root).verify(
        _bundle([{"command": "python -m pytest -V", "exit_code": 0}])
    )
    assert res["overall_trust"] not in {"HIGH"}
