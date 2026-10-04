import importlib.util
import json
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).parents[2]
PATH = ROOT / "scripts" / "ops" / "nexus-hermes-controller-guard"
LOADER = SourceFileLoader("hermes_guard", str(PATH))
SPEC = importlib.util.spec_from_loader("hermes_guard", LOADER)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MOD)


def doctor(disposition, gate="CONTINUE_BOUNDED_ISSUE_WORK"):
    return {
        "schema": "nexus.workflow_doctor.v1",
        "claim_ceiling": "READ_ONLY_WORKFLOW_OBSERVATION",
        "resume_disposition": disposition,
        "next_gate": {"code": gate},
    }


def test_doctor_safe_continues_only_exact_gate():
    assert MOD.classify_doctor(doctor("SAFE")) == {
        "decision": "CONTINUE_EXACT_NEXT_GATE",
        "next_gate": "CONTINUE_BOUNDED_ISSUE_WORK",
    }


def test_doctor_safe_terminal_is_noop():
    assert MOD.classify_doctor(doctor("SAFE", "NO_PENDING_GATE")) == {
        "decision": "NOOP_TERMINAL",
        "next_gate": "NO_PENDING_GATE",
    }


def test_doctor_wait_reconcile_blocked_fail_closed():
    assert MOD.classify_doctor(doctor("WAIT"))["decision"] == "WAIT"
    assert MOD.classify_doctor(doctor("RECONCILE"))["decision"] == "RECONCILE_EXISTING_EFFECT"
    assert MOD.classify_doctor(doctor("BLOCKED"))["decision"] == "BLOCK"


def test_doctor_unknown_or_wrong_schema_blocks():
    assert MOD.classify_doctor(doctor("SOMETHING_NEW"))["decision"] == "BLOCK_UNKNOWN"
    bad = doctor("SAFE")
    bad["schema"] = "unexpected"
    assert MOD.classify_doctor(bad)["decision"] == "BLOCK_UNKNOWN"


def test_escalation_is_deterministic_and_advisory():
    local = MOD.escalation_decision({"same_gate_failures": 1})
    assert local["decision"] == "LOCAL_CONTINUE"
    assert local["escalate"] is False

    escalated = MOD.escalation_decision(
        {
            "same_gate_failures": 2,
            "evidence_conflict": True,
            "authority_boundary_change": False,
        }
    )
    assert escalated["decision"] == "ASK_FRONTIER_ADVISER"
    assert escalated["authority"] == "ADVISORY_ONLY"
    assert "REPEATED_GATE_FAILURE" in escalated["reasons"]
    assert "EVIDENCE_CONFLICT" in escalated["reasons"]


def test_multi_cause_requires_exhausted_falsification():
    not_yet = MOD.escalation_decision(
        {"plausible_root_causes": 3, "bounded_falsification_exhausted": False}
    )
    assert not_yet["decision"] == "LOCAL_CONTINUE"

    ready = MOD.escalation_decision(
        {"plausible_root_causes": 2, "bounded_falsification_exhausted": True}
    )
    assert ready["decision"] == "ASK_FRONTIER_ADVISER"


def test_require_safe_cli_blocks_non_safe_doctor(tmp_path):
    payload = doctor("BLOCKED", "SOURCE_IDENTITY_UNAVAILABLE")
    path = tmp_path / "doctor.json"
    path.write_text(json.dumps(payload))
    result = subprocess.run(
        [str(PATH), "doctor", "--input", str(path), "--require-safe"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["decision"] == "BLOCK"


def test_require_safe_cli_allows_safe_terminal_observation(tmp_path):
    path = tmp_path / "doctor.json"
    path.write_text(json.dumps(doctor("SAFE", "NO_PENDING_GATE")))
    result = subprocess.run(
        [str(PATH), "doctor", "--input", str(path), "--require-safe"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "NOOP_TERMINAL"
