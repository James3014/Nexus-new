from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "frontier_b_handoff_canary.py"
RECEIPT = ROOT / "docs" / "ops" / "frontier_b_cross_session_canary_v1.json"
spec = importlib.util.spec_from_file_location("frontier_b_handoff_canary", SCRIPT)
assert spec and spec.loader
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

SOURCE = "git-commit:4c9e1481346ee62f3adcdcd4ba3538e3564a8e03"


def test_recorded_canary_recovers_non_terminal_workflow_without_chat():
    receipt = M.load_receipt(RECEIPT)
    recovered = M.recover_from_receipt(receipt, current_source_revision=SOURCE)
    assert recovered["resume_disposition"] == "SAFE"
    assert recovered["task_id"] == "frontier-b-1188-cross-session-canary"
    assert recovered["operation_id"] == "frontier-b-op-1188-closeout"
    assert recovered["attempt_id"] == "frontier-b-attempt-1"
    assert recovered["next_gate"] == "VERIFY_PARENT_CLOSEOUT"
    assert recovered["chat_memory_required"] is False
    assert recovered["completed_effects_replay_allowed"] is False
    assert len(recovered["completed_effects"]) == 7
    assert all(row["replay_allowed"] is False for row in recovered["completed_effects"])


def test_fresh_process_reads_only_durable_receipt():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(RECEIPT),
            "--current-source",
            SOURCE,
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    recovered = json.loads(proc.stdout)
    assert recovered["resume_disposition"] == "SAFE"
    assert recovered["next_gate"] == "VERIFY_PARENT_CLOSEOUT"
    assert recovered["completed_effects_replay_allowed"] is False


def test_source_drift_forces_reconciliation_before_resume():
    receipt = M.load_receipt(RECEIPT)
    recovered = M.recover_from_receipt(
        receipt,
        current_source_revision="git-commit:" + "0" * 40,
    )
    assert recovered["resume_disposition"] == "RECONCILE"
    assert recovered["reason"] == "SOURCE_IDENTITY_DRIFT"


def test_all_seven_owner_contracts_are_terminal_and_unique():
    receipt = M.load_receipt(RECEIPT)
    owners = receipt["owner_contracts"]
    assert len(owners) == 7
    assert len({row["repository"] for row in owners}) == 7
    assert all(row["issue_state"] == "CLOSED" for row in owners)
    assert all(row["pr_state"] == "MERGED" for row in owners)


def test_required_advisory_and_deployment_closeout_are_separate():
    receipt = M.load_receipt(RECEIPT)
    policy = receipt["required_vs_advisory"]
    assert policy["required_gates"] == ["test"]
    assert set(policy["required_gates"]).isdisjoint(policy["advisory_observers"])
    assert policy["advisory_failure_blocks_merge"] is False
    assert receipt["doctor"]["read_only"] is True
    assert receipt["deployment_closeout_path"]["steps"][-2:] == [
        "bounded_canary",
        "rollback_receipt",
    ]


def test_receipt_tamper_is_detected():
    receipt = M.load_receipt(RECEIPT)
    tampered = copy.deepcopy(receipt)
    tampered["checkpoint"]["attempt_id"] = "other-attempt"
    with pytest.raises(M.CanaryError, match="checkpoint hash mismatch"):
        M.validate_receipt(tampered)
