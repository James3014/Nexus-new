"""Evidence without a real passing replay must not be VERIFIED (unless explicitly waived)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "evidence_verifier.py"
REPLAY_CMD = {"command": "python3 -m pytest --version", "exit_code": 0}


def _env() -> dict[str, str]:
    # The replay runner resolves `python3` from PATH; make it the interpreter running the tests.
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def _run(tmp_path: Path, test_artifacts: list, *extra: str) -> tuple[int, dict]:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps({
            "final_response": "The task is ready for review.",
            "evidence_bundle": {"code_artifacts": ["app.py"], "test_artifacts": test_artifacts},
        }),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(evidence), *extra],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        env=_env(),
    )
    start = proc.stdout.index("{\n")
    return proc.returncode, json.loads(proc.stdout[start:])


@pytest.mark.parametrize("notes", [["claims_count=7"], [{"aggregates": {"success_rate": 1.0}}]])
def test_notes_only_evidence_is_not_verified(tmp_path, notes):
    code, data = _run(tmp_path, notes)
    assert data["status"] == "UNVERIFIED"
    assert data["status"] != "VERIFIED"
    assert data["overall_trust"] == "LOW"
    assert data["reason"] == "NO_REPLAYABLE_COMMANDS"
    assert data["replay_verified"] is False
    assert data["replay_waived"] is False
    assert code != 0


def test_notes_only_allowed_only_with_explicit_flag_and_is_labelled(tmp_path):
    code, data = _run(tmp_path, ["claims_count=7"], "--allow-no-replay")
    assert code == 0
    assert data["status"] == "VERIFIED"
    assert data["replay_verified"] is False
    assert data["replay_waived"] is True
    assert data["overall_trust"] == "MEDIUM"
    assert "waived" in data["message"]


def test_allowlisted_passing_command_is_verified(tmp_path):
    code, data = _run(tmp_path, [REPLAY_CMD])
    assert code == 0
    assert data["status"] == "VERIFIED"
    assert data["overall_trust"] == "HIGH"
    assert data["replay_verified"] is True
    assert data["replay_waived"] is False


def test_failing_allowlisted_command_is_rejected(tmp_path):
    code, data = _run(tmp_path, [{"command": "python3 -m pytest --version", "exit_code": 7}])
    assert data["status"] == "REJECTED"
    assert code != 0


def _delivery_verifier():
    from nexus.delivery.evidence_verifier import EvidenceVerifier

    return EvidenceVerifier(ROOT)


def _bundle(test_artifacts: list) -> dict:
    return {"version": "1.1.0", "code_artifacts": ["README.md"], "test_artifacts": test_artifacts}


def test_delivery_verifier_notes_only_is_unverified():
    with patch("nexus.delivery.anti_drift.AntiDrift.verify_drift", return_value=(True, {})):
        res = _delivery_verifier().verify(_bundle(["claims_count=7"]))
    # #2624: no replayable command is an advisory coverage gap, never VERIFIED nor REJECTED.
    assert res["status"] == "UNCOVERED"
    assert res["advisory"] is True
    assert res["overall_trust"] not in {"HIGH", "MEDIUM"}
    assert res["reason"] == "no_replayable_commands"
    assert res["replay_verified"] is False
    assert res["replay_waived"] is False


def test_delivery_verifier_no_test_artifacts_is_uncovered_advisory():
    with (
        patch("nexus.delivery.anti_drift.AntiDrift.verify_drift", return_value=(True, {})),
        patch(
            "nexus.delivery.evidence_verifier.EvidenceVerifier._check_git_diff_non_empty",
            return_value=True,
        ),
    ):
        res = _delivery_verifier().verify(_bundle([]))
    assert res["status"] == "UNCOVERED"
    assert res["advisory"] is True
    assert res["status"] not in {"VERIFIED", "REJECTED"}
    # Advisory only: not verified (never HIGH/MEDIUM) and not a LOW-trust rejection either.
    assert res["overall_trust"] == "UNKNOWN"
    assert res["reject_reasons"] == []


def test_delivery_verifier_uncovered_with_empty_diff_stays_low_trust():
    with (
        patch("nexus.delivery.anti_drift.AntiDrift.verify_drift", return_value=(True, {})),
        patch(
            "nexus.delivery.evidence_verifier.EvidenceVerifier._check_git_diff_non_empty",
            return_value=False,
        ),
    ):
        res = _delivery_verifier().verify(_bundle(["claims_count=7"]))
    assert res["status"] == "UNCOVERED"
    assert res["overall_trust"] == "LOW"
    assert "empty_git_diff" in res["reject_reasons"]


def test_delivery_verifier_uncovered_never_executes_notes(monkeypatch):
    import subprocess as _sp

    real_run = _sp.run
    seen: list = []

    def _spy(args, *a, **k):
        seen.append(args)
        return real_run(args, *a, **k)

    monkeypatch.setattr("nexus.delivery.evidence_verifier.subprocess.run", _spy)
    with patch("nexus.delivery.anti_drift.AntiDrift.verify_drift", return_value=(True, {})):
        res = _delivery_verifier().verify(_bundle(["touch /tmp/nexus_2624_should_not_run"]))
    assert res["status"] == "UNCOVERED"
    assert all(isinstance(a, list) and a[0] == "git" for a in seen), seen


def test_delivery_verifier_notes_only_allowed_is_labelled_and_capped():
    with patch("nexus.delivery.anti_drift.AntiDrift.verify_drift", return_value=(True, {})):
        res = _delivery_verifier().verify(_bundle(["claims_count=7"]), allow_no_replay=True)
    assert res["replay_verified"] is False
    assert res["replay_waived"] is True
    assert res["overall_trust"] != "HIGH"


def test_delivery_verifier_real_replay_is_marked_verified():
    with (
        patch("nexus.delivery.anti_drift.AntiDrift.verify_drift", return_value=(True, {})),
        patch.dict(os.environ, _env()),
    ):
        res = _delivery_verifier().verify(_bundle([REPLAY_CMD]))
    assert res.get("status") != "UNVERIFIED"
    assert res["replay_verified"] is True
    assert res["replay_waived"] is False
