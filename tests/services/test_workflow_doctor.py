"""Regression tests for the read-only Nexus workflow doctor."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

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


def test_source_no_effect_reconciled_failure_releases_reconcile_gate() -> None:
    operation = _no_operation()
    operation["requested_id"] = "agyop_" + "2" * 32
    operation["selected"] = {
        "operation_id": operation["requested_id"],
        "status": "FAILED",
        "reconciliation": {
            "result": "SOURCE_NO_DURABLE_EFFECT_PROVEN",
            "reconciliation_scope": "SOURCE_ONLY",
            "retry_permitted": True,
        },
    }

    disposition, gate = doctor._derive_next_gate(
        source=_base_source(),
        runtime=_base_runtime(),
        task={"status": "OBSERVED", "state": "open", "issue_number": 1274},
        operation=operation,
        pr={"status": "NOT_REQUESTED", "pr_number": None},
        required_gates=[],
        leases=_no_leases(),
    )

    assert disposition == "SAFE"
    assert gate["code"] == "CONTINUE_BOUNDED_ISSUE_WORK"


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


# ---------------------------------------------------------------------------
# resolve_workflow_repo_root
# ---------------------------------------------------------------------------


def test_resolve_repo_root_omitted_uses_canonical_not_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When repo_root is omitted the canonical root, not cwd, is the candidate."""
    monkeypatch.chdir(tmp_path)  # cwd is now an unrelated tmp dir
    monkeypatch.setattr(doctor, "CANONICAL_SOURCE_ROOT", ROOT)

    result = doctor.resolve_workflow_repo_root(None, None)

    assert result == ROOT.expanduser().resolve()
    assert result != tmp_path


def test_resolve_repo_root_explicit_with_mismatched_repository_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit repo_root + non-matching repository raises RuntimeError (fails closed)."""

    def _fake_resolve(*, expected_repository: str, canonical_root: Path | None) -> Path:
        raise RuntimeError("RDC_REPO_ROOT_REMOTE_MISMATCH")

    monkeypatch.setattr(doctor, "resolve_rdc_repo_root", _fake_resolve)

    with pytest.raises(RuntimeError, match="RDC_REPO_ROOT_REMOTE_MISMATCH"):
        doctor.resolve_workflow_repo_root(str(tmp_path), "owner/other-repo")


def test_resolve_repo_root_omitted_repository_preserves_canonical_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitted repository preserves canonical root without inventing a slug."""
    monkeypatch.setattr(doctor, "CANONICAL_SOURCE_ROOT", ROOT)

    result = doctor.resolve_workflow_repo_root(None, None)

    # Must resolve to the canonical root, not to some fabricated path.
    assert result == ROOT.expanduser().resolve()


def test_build_parser_repo_root_default_is_none() -> None:
    """--repo-root default must be None so cwd is never silently injected."""
    parser = doctor.build_parser()
    args = parser.parse_args([])
    assert args.repo_root is None


def test_workflow_doctor_reconcile_required_operation_projects_reconcile_gate() -> None:
    """An operation in RECONCILE_REQUIRED triggers RECONCILE gate instead of WAIT or SAFE."""
    op = _no_operation()
    op["active"] = [
        {"operation_id": "agyop_123", "phase": "RECONCILE_REQUIRED", "status": "RUNNING"}
    ]
    disposition, next_action = doctor._derive_next_gate(
        source=_base_source(),
        runtime=_base_runtime(),
        task={"status": "OBSERVED", "state": "open", "issue_number": 1373},
        operation=op,
        pr={"status": "NONE", "pr_number": None},
        required_gates=[],
        leases=_no_leases(),
    )
    assert disposition == "RECONCILE"
    assert next_action["code"] == "RECONCILE_OPERATION"
    assert "agyop_123" in next_action["operation_ids"]


def test_workflow_doctor_collects_claimed_at_and_consumer_id(tmp_path: Path) -> None:
    """_collect_leases accurately reads claimed_at and consumer_id from receipt."""
    leases_dir = tmp_path / ".nexus" / "agy-account-pool" / "leases"
    leases_dir.mkdir(parents=True)
    receipt_data = {
        "account_alias_hash": "alias123",
        "lease_id_hash": "lease456",
        "consumer_id": "hcom_collab:1234:abc",
        "pid": 5678,
        "claimed_at": 1728000000.0,
    }
    (leases_dir / "alias123.receipt.json").write_text(json.dumps(receipt_data), encoding="utf-8")
    collected = doctor._collect_leases(tmp_path)
    assert len(collected["active"]) == 1
    item = collected["active"][0]
    assert item["account_alias_hash"] == "alias123"
    assert item["lease_id_hash"] == "lease456"
    assert item["consumer_id"] == "hcom_collab:1234:abc"
    assert item["claimed_at"] == 1728000000.0


# ---------------------------------------------------------------------------
# Issue #1436 Wave 1 RED contract: false-completion projection
# ---------------------------------------------------------------------------


def _completion_layers(payload: dict) -> dict[str, dict]:
    """Return completion rows without freezing the final public wrapper name."""
    matrix = payload.get("completion_matrix") or payload.get("completion")
    assert matrix is not None, (
        "Issue #1436 requires a current read-only completion projection; "
        "workflow doctor currently exposes no completion-layer view"
    )
    rows = matrix.get("layers") if isinstance(matrix, dict) else matrix
    assert isinstance(rows, list), "completion projection must expose independent layer rows"
    return {str(row["layer"]): row for row in rows}


def _collect_with_observations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    source: dict | None = None,
    runtime: dict | None = None,
    operation: dict | None = None,
    pr: dict | None = None,
    task: dict | None = None,
) -> dict:
    """Exercise collect_workflow_doctor through producer-shaped read-only observations."""
    repository = "James3014/Nexus-new"
    source = source or {
        "status": "OBSERVED",
        "repository": repository,
        "github_main": "b" * 40,
        "head": "b" * 40,
        "head_is_github_main": True,
    }
    runtime = runtime or {
        "status": "OBSERVED",
        "state": "INSTALLED",
        "installed_revision": "b" * 40,
        "components": {},
    }
    operation = operation or _no_operation()
    pr = pr or {"status": "NOT_REQUESTED", "pr_number": None}
    task = task or {
        "status": "OBSERVED",
        "state": "open",
        "issue_number": 1436,
    }

    monkeypatch.setattr(
        doctor,
        "_collect_source",
        lambda *args, **kwargs: (dict(source), repository),
    )
    monkeypatch.setattr(doctor, "_collect_task", lambda *args, **kwargs: dict(task))
    monkeypatch.setattr(
        doctor,
        "_collect_pr",
        lambda *args, **kwargs: (dict(pr), [], [], []),
    )
    monkeypatch.setattr(doctor, "_collect_runtime", lambda *args, **kwargs: dict(runtime))
    monkeypatch.setattr(
        doctor,
        "_collect_quota_snapshot",
        lambda *args, **kwargs: {"status": "UNAVAILABLE", "accounts": []},
    )
    monkeypatch.setattr(
        doctor,
        "_collect_operations",
        lambda *args, **kwargs: dict(operation),
    )
    monkeypatch.setattr(doctor, "_collect_leases", lambda *args, **kwargs: _no_leases())

    return doctor.collect_workflow_doctor(
        repo_root=tmp_path,
        repository=repository,
        issue_number=1436,
        pr_number=pr.get("pr_number"),
        home=tmp_path,
    )


def test_completion_projection_keeps_merged_integration_separate_from_runtime_unknown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PR integration evidence must not make runtime/native-entrypoint evidence green."""
    payload = _collect_with_observations(
        monkeypatch,
        tmp_path,
        runtime={
            "status": "UNAVAILABLE",
            "error": "NEXUS_HOST_SYNC_NOT_FOUND",
            "components": {},
        },
        pr={
            "status": "OBSERVED",
            "state": "closed",
            "merged": True,
            "pr_number": 1437,
            "head_sha": "b" * 40,
            "merge_commit_sha": "b" * 40,
        },
    )

    layers = _completion_layers(payload)

    assert payload["completion_matrix"]["claim_ceiling"] == (
        "READ_ONLY_PROJECTION_NO_COMPLETION_AUTHORITY"
    )
    assert layers["Integration"]["status"] == "PASS"
    assert layers["Runtime"]["status"] != "PASS"
    assert layers["Native / real entrypoint"]["status"] != "PASS"


def test_completion_projection_rejects_pass_bound_to_previous_candidate_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A PASS for Candidate A must not silently satisfy changed Candidate B."""
    operation = _no_operation()
    operation["selected"] = {
        "operation_id": "agyop_" + "1" * 32,
        "status": "COMPLETED",
        "phase": "TERMINAL",
        "review_candidate_head": "a" * 40,
        "candidate_digest": "c" * 64,
        "current_candidate_digest": "d" * 64,
        "review_state": "TERMINAL",
        "review_verdict": "ACCEPT",
        "review_applicable": False,
        "subject_stable": False,
    }

    payload = _collect_with_observations(
        monkeypatch,
        tmp_path,
        operation=operation,
    )
    layers = _completion_layers(payload)

    source_verification = layers["Source verification"]
    assert source_verification["status"] != "PASS"
    assert source_verification["revision"] == "b" * 40
    assert source_verification.get("gap")


def test_pre_gate_review_cannot_project_independent_acceptance_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A review-only PRE-GATE may not mint post-Candidate acceptance truth."""
    operation = _no_operation()
    operation["selected"] = {
        "operation_id": "agyop_" + "2" * 32,
        "status": "COMPLETED",
        "phase": "TERMINAL",
        "review_effect_id": "e" * 64,
        "review_candidate_head": "b" * 40,
        "candidate_digest": "d" * 64,
        "current_candidate_digest": "d" * 64,
        "review_state": "TERMINAL",
        "review_verdict": "ACCEPT",
        "review_applicable": True,
        "subject_stable": True,
    }

    payload = _collect_with_observations(
        monkeypatch,
        tmp_path,
        operation=operation,
    )
    layers = _completion_layers(payload)

    acceptance = layers["Independent acceptance"]
    assert acceptance["status"] != "PASS"
    assert acceptance["source"] == "direct_operation_review"
    assert acceptance["gap"] == "INDEPENDENT_ACCEPTANCE_AUTHORITY_NOT_OBSERVED"
