"""Regression tests for the read-only Nexus workflow doctor."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

from nexus.services import workflow_doctor as doctor

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_workflow_doctor.sh"
ENTRYPOINT = ROOT / "scripts" / "ops" / "nexus-workflow-doctor"


def _base_source() -> dict:
    return {
        "status": "OBSERVED",
        "github_main": "a" * 40,
        "head": "a" * 40,
    }


def _base_runtime() -> dict:
    return {
        "status": "OBSERVED",
        "state": "INSTALLED",
        "installed_revision": "a" * 40,
        "components": {
            "host_sync": {"status": "VERIFIED"},
            "workflow_doctor": {"status": "VERIFIED"},
        },
    }


def _no_operation() -> dict:
    return {
        "requested_id": None,
        "selected": None,
        "selected_error": None,
        "active": [],
        "latest_terminal": None,
    }


def _no_leases() -> dict:
    return {
        "active": [],
        "family_unavailable": [],
        "quarantined": [],
    }


def test_required_check_names_reads_applied_rules() -> None:
    required, state = doctor._required_check_names([
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": "Exact-base impact gate"},
                    {"context": "Trusted verifier (default branch)"},
                ]
            },
        }
    ])

    assert state == "OBSERVED"
    assert required == {
        "Exact-base impact gate",
        "Trusted verifier (default branch)",
    }


def test_advisory_failure_does_not_block_exact_head_merge_gate() -> None:
    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=_base_runtime(),
        task={"status": "NOT_REQUESTED"},
        operation=_no_operation(),
        pr={
            "status": "OBSERVED",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "pr_number": 1188,
        },
        required_gates=[
            {
                "name": "Exact-base impact gate",
                "status": "completed",
                "conclusion": "success",
            }
        ],
        leases=_no_leases(),
    )

    assert disposition == "SAFE"
    assert gate["code"] == "EXACT_HEAD_MERGE_GATE"


def test_runtime_main_drift_requires_reconcile() -> None:
    runtime = _base_runtime()
    runtime["installed_revision"] = "c" * 40

    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=runtime,
        task={"status": "NOT_REQUESTED"},
        operation=_no_operation(),
        pr={"status": "NOT_REQUESTED"},
        required_gates=[],
        leases=_no_leases(),
    )

    assert disposition == "RECONCILE"
    assert gate["code"] == "SYNC_RUNTIME_TO_CURRENT_MAIN"


def test_content_equivalent_last_sync_is_current_main_aligned() -> None:
    runtime = _base_runtime()
    runtime["installed_revision"] = "c" * 40
    runtime["installed_bundle_sha256"] = "bundle"
    runtime["last_sync"] = {
        "state": "ALIGNED",
        "desired_revision": "a" * 40,
        "desired_bundle_sha256": "bundle",
        "installed_bundle_sha256": "bundle",
    }

    alignment = doctor._runtime_main_alignment(runtime, "a" * 40)
    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=runtime,
        task={"status": "NOT_REQUESTED", "issue_number": None},
        operation=_no_operation(),
        pr={"status": "NOT_REQUESTED", "pr_number": None},
        required_gates=[],
        leases=_no_leases(),
    )

    assert alignment["status"] == "ALIGNED"
    assert alignment["basis"] == "CONTENT_EQUIVALENT_LAST_SYNC"
    assert disposition == "SAFE"
    assert gate["code"] == "NO_PENDING_GATE"


def test_open_pr_gates_take_precedence_over_unrelated_runtime_drift() -> None:
    runtime = _base_runtime()
    runtime["installed_revision"] = "c" * 40

    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=runtime,
        task={"status": "OBSERVED", "state": "open", "issue_number": 1188},
        operation=_no_operation(),
        pr={
            "pr_number": 1191,
            "status": "OBSERVED",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "gate_policy_state": "OBSERVED",
            "check_observation_error": None,
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
        },
        required_gates=[
            {
                "name": "Exact-base impact gate",
                "status": "completed",
                "conclusion": "success",
            }
        ],
        leases=_no_leases(),
    )

    assert disposition == "SAFE"
    assert gate["code"] == "EXACT_HEAD_MERGE_GATE"


def test_closed_pr_exposes_runtime_sync_as_closeout_gate() -> None:
    runtime = _base_runtime()
    runtime["installed_revision"] = "c" * 40

    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=runtime,
        task={"status": "OBSERVED", "state": "open", "issue_number": 1188},
        operation=_no_operation(),
        pr={
            "pr_number": 1191,
            "status": "OBSERVED",
            "state": "closed",
        },
        required_gates=[],
        leases=_no_leases(),
    )

    assert disposition == "RECONCILE"
    assert gate["code"] == "SYNC_RUNTIME_TO_CURRENT_MAIN"


def test_outcome_unknown_operation_requires_reconcile() -> None:
    operation = _no_operation()
    operation["requested_id"] = "agyop_" + "1" * 32
    operation["selected"] = {
        "operation_id": operation["requested_id"],
        "status": "OUTCOME_UNKNOWN",
    }

    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=_base_runtime(),
        task={"status": "NOT_REQUESTED"},
        operation=operation,
        pr={"status": "NOT_REQUESTED"},
        required_gates=[],
        leases=_no_leases(),
    )

    assert disposition == "RECONCILE"
    assert gate["code"] == "RECONCILE_OPERATION"


def test_quota_snapshot_projection_omits_email(tmp_path: Path) -> None:
    home = tmp_path
    path = home / ".nexus/agy-account-pool/quota-snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "checked_at": "2026-09-28T23:00:00+00:00",
            "accounts": [
                {
                    "account": "google-08",
                    "email": "secret@example.invalid",
                    "ok": True,
                    "checked_at": "2026-09-28T23:00:00+00:00",
                    "groups": {
                        "Gemini Models": {
                            "5h": {
                                "status": "known",
                                "remaining_pct": 80.0,
                                "reset_at": None,
                            }
                        }
                    },
                }
            ],
        }),
        encoding="utf-8",
    )

    projected = doctor._collect_quota_snapshot(home)

    assert projected["status"] == "OBSERVED"
    assert projected["account_count"] == 1
    assert projected["accounts"][0]["account"] == "google-08"
    assert "email" not in projected["accounts"][0]


def test_unknown_required_gate_policy_blocks_merge_readiness() -> None:
    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=_base_runtime(),
        task={"status": "NOT_REQUESTED"},
        operation=_no_operation(),
        pr={
            "status": "OBSERVED",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "pr_number": 1188,
            "gate_policy_state": "UNKNOWN",
            "gate_policy_error": "rules unavailable",
        },
        required_gates=[],
        leases=_no_leases(),
    )

    assert disposition == "BLOCKED"
    assert gate["code"] == "VERIFY_REQUIRED_GATE_POLICY"


def test_unrelated_active_lease_is_observation_not_generic_workflow_blocker() -> None:
    leases = _no_leases()
    leases["active"] = [{"account_alias_hash": "hash", "lease_id_hash": "lease"}]

    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=_base_runtime(),
        task={"status": "OBSERVED", "state": "open", "issue_number": 1188},
        operation=_no_operation(),
        pr={"status": "NOT_REQUESTED"},
        required_gates=[],
        leases=leases,
    )

    assert disposition == "SAFE"
    assert gate["code"] == "CONTINUE_BOUNDED_ISSUE_WORK"


def test_installer_deploys_exact_canonical_entrypoint(tmp_path: Path) -> None:
    target = tmp_path / "nexus-workflow-doctor"
    env = os.environ.copy()
    env.update({
        "NEXUS_WORKFLOW_DOCTOR_REPO_ROOT": str(ROOT),
        "NEXUS_WORKFLOW_DOCTOR_TARGET": str(target),
    })

    proc = subprocess.run(
        ["bash", str(INSTALLER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == ENTRYPOINT.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_operation_projection_exposes_bounded_review_identity(tmp_path: Path) -> None:
    operation_path = tmp_path / "operation.json"
    operation_path.write_text(
        json.dumps({
            "schema": "nexus.agy_operation.v1",
            "operation_id": "agyop_" + ("a" * 32),
            "attempt_id": "attempt_" + ("b" * 32),
            "status": "COMPLETED",
            "phase": "TERMINAL",
            "review_effect_id": "c" * 64,
            "review_role": "independent-acceptance",
            "candidate_digest": "d" * 64,
            "review_packet_sha256": "e" * 64,
            "review_state": "TERMINAL",
            "review_verdict": "ACCEPT",
            "review_applicable": True,
            "subject_stable": True,
            "private_review_secret": "not-public",
        }),
        encoding="utf-8",
    )

    projected = doctor._read_operation(operation_path)

    assert projected["review_effect_id"] == "c" * 64
    assert projected["candidate_digest"] == "d" * 64
    assert projected["review_packet_sha256"] == "e" * 64
    assert projected["review_verdict"] == "ACCEPT"
    assert projected["review_applicable"] is True
    assert "private_review_secret" not in projected
