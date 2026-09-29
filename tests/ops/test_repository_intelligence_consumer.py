"""Tests for Repository Intelligence terminal consumer integration (#1200)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services import workflow_doctor as doctor
from scripts.ops.verify_repository_intelligence_terminal import (
    CHECK_ROLE_CLAIM_CEILING,
    CHECK_ROLE_SCHEMA,
    PINNED_ACTION_COMMIT,
    RepositoryIntelligenceConsumerError,
    canonical_hash,
    verify_advisory_terminal_evidence,
)

IDENTITY = {
    "repository": "James3014/Nexus-new",
    "pr_number": 1191,
    "head_sha": "a87f287ad8e917b4980e7ea05729e32010e8ad5a",
    "base_sha": "c0270bdb207cf9c07e2510bcefd199959971ca17",
    "current_main_sha": "c0270bdb207cf9c07e2510bcefd199959971ca17",
}


def _valid_terminal_bundle() -> dict:
    review_identity = [
        IDENTITY["repository"],
        IDENTITY["pr_number"],
        IDENTITY["head_sha"],
        IDENTITY["base_sha"],
        IDENTITY["current_main_sha"],
    ]
    cloud_bundle = {
        "schema": "reviewer.repository_intelligence_cloud.v1",
        "claim_ceiling": "ADVISORY_EVIDENCE_ONLY",
        "review_identity": review_identity,
        "reports": {},
    }
    cloud_bundle["content_sha256"] = canonical_hash(cloud_bundle)

    terminal_observation = {
        "schema": "reviewer.repository_intelligence_terminal_observation.v1",
        "semantics": "OBSERVED_CHECK_SET_TERMINAL_AFTER_QUIESCENCE",
        "expected_head_sha": IDENTITY["head_sha"],
        "observed_external_check_count": 1,
        "observed_checks": [
            {
                "name": "Exact-base impact gate",
                "status": "success",
                "head_sha": IDENTITY["head_sha"],
            }
        ],
    }
    bundle = {
        "schema": "reviewer.repository_intelligence_terminal_cloud.v1",
        "claim_ceiling": "ADVISORY_EVIDENCE_ONLY",
        "snapshot_semantics": "OBSERVED_CHECK_SET_TERMINAL_AFTER_QUIESCENCE",
        "review_identity": review_identity,
        "terminal_observation": terminal_observation,
        "cloud_bundle": cloud_bundle,
    }
    bundle["content_sha256"] = canonical_hash(bundle)
    return bundle


def test_action_commit_pinned_to_pr34():
    assert PINNED_ACTION_COMMIT == "b1a0bd882e37a08a3a540947ae767a23d752bd67"


def test_timeout_fixture_produces_valid_advisory_incomplete_evidence(tmp_path: Path):
    """Timeout produces valid ADVISORY_INCOMPLETE evidence without required-failure signal."""
    report_file = tmp_path / "terminal.json"
    result = verify_advisory_terminal_evidence(
        report_path=report_file,
        action_outcome="failure",
        identity=IDENTITY,
        action_commit=PINNED_ACTION_COMMIT,
    )

    assert result["schema"] == CHECK_ROLE_SCHEMA
    assert result["advisory_disposition"] == "ADVISORY_INCOMPLETE"
    assert result["observer_health"] == "DEGRADED"
    assert result["required_gate_state"] == "CLEAR"
    assert result["action_commit"] == PINNED_ACTION_COMMIT
    assert result["review_identity"] == IDENTITY
    assert result["claim_ceiling"] == CHECK_ROLE_CLAIM_CEILING
    assert report_file.is_file()

    written = json.loads(report_file.read_text(encoding="utf-8"))
    assert written == result
    unsigned = {k: v for k, v in result.items() if k != "content_sha256"}
    assert canonical_hash(unsigned) == result["content_sha256"]


def test_successful_action_validates_and_records_commit_sha(tmp_path: Path):
    """Successful terminal observation validates envelope and records exact commit SHA."""
    report_file = tmp_path / "terminal.json"
    bundle = _valid_terminal_bundle()
    report_file.write_text(json.dumps(bundle), encoding="utf-8")

    result = verify_advisory_terminal_evidence(
        report_path=report_file,
        action_outcome="success",
        identity=IDENTITY,
        action_commit=PINNED_ACTION_COMMIT,
    )

    assert result["action_commit"] == PINNED_ACTION_COMMIT
    assert len(result["content_sha256"]) == 64
    assert result["claim_ceiling"] == "ADVISORY_EVIDENCE_ONLY"


def test_successful_action_rejects_stale_review_identity(tmp_path: Path):
    report_file = tmp_path / "stale.json"
    bundle = _valid_terminal_bundle()
    bundle["review_identity"][2] = "0" * 40
    bundle["content_sha256"] = canonical_hash(
        {k: v for k, v in bundle.items() if k != "content_sha256"}
    )
    report_file.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(RepositoryIntelligenceConsumerError, match="REVIEW_IDENTITY_MISMATCH"):
        verify_advisory_terminal_evidence(
            report_path=report_file,
            action_outcome="success",
            identity=IDENTITY,
        )


def test_successful_action_rejects_tampered_terminal_bundle(tmp_path: Path):
    report_file = tmp_path / "tampered.json"
    bundle = _valid_terminal_bundle()
    bundle["terminal_observation"]["observed_external_check_count"] = 2
    report_file.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(
        RepositoryIntelligenceConsumerError,
        match="TERMINAL_BUNDLE_CONTENT_SHA256_MISMATCH",
    ):
        verify_advisory_terminal_evidence(
            report_path=report_file,
            action_outcome="success",
            identity=IDENTITY,
        )


def test_malformed_evidence_fails_visibly(tmp_path: Path):
    """Malformed or invalid JSON evidence fails visibly."""
    report_file = tmp_path / "corrupt.json"
    report_file.write_text("not json", encoding="utf-8")

    with pytest.raises(RepositoryIntelligenceConsumerError, match="MALFORMED_EVIDENCE_JSON"):
        verify_advisory_terminal_evidence(
            report_path=report_file,
            action_outcome="success",
            identity=IDENTITY,
        )


def test_invalid_claim_ceiling_fails_visibly(tmp_path: Path):
    """Unauthorized claim ceiling in evidence fails visibly."""
    report_file = tmp_path / "invalid_ceiling.json"
    bundle = {
        "schema": "reviewer.repository_intelligence_terminal_cloud.v1",
        "claim_ceiling": "UNAUTHORIZED_PRODUCTION_AUTHORITY",
        "content_sha256": "1" * 64,
    }
    report_file.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(RepositoryIntelligenceConsumerError, match="INVALID_CLAIM_CEILING"):
        verify_advisory_terminal_evidence(
            report_path=report_file,
            action_outcome="success",
            identity=IDENTITY,
        )


def test_scenario_1191_truthful_rendering_in_workflow_doctor():
    """Scenario #1191: required gates green + advisory terminal incomplete.

    Renders truthfully in workflow doctor: advisory observer is classified as
    ADVISORY_INCOMPLETE, required gates remain CLEAR, and resume disposition is SAFE
    with EXACT_HEAD_MERGE_GATE.
    """
    required_gates = [
        {
            "name": "Exact-base impact gate",
            "policy_role": "REQUIRED_GATE",
            "status": "completed",
            "conclusion": "success",
        },
        {
            "name": "Trusted verifier (default branch)",
            "policy_role": "REQUIRED_GATE",
            "status": "completed",
            "conclusion": "success",
        },
        {
            "name": "Full published Git history secret audit",
            "policy_role": "REQUIRED_GATE",
            "status": "completed",
            "conclusion": "success",
        },
    ]

    disposition, gate = doctor._derive_next_gate(
        source={
            "status": "OBSERVED",
            "github_main": IDENTITY["base_sha"],
            "head": IDENTITY["base_sha"],
        },
        runtime={
            "status": "OBSERVED",
            "state": "INSTALLED",
            "installed_revision": IDENTITY["base_sha"],
            "components": {
                "host_sync": {"status": "VERIFIED"},
                "workflow_doctor": {"status": "VERIFIED"},
            },
        },
        task={"status": "OBSERVED", "state": "open", "issue_number": 1188},
        operation={
            "requested_id": None,
            "selected": None,
            "selected_error": None,
            "active": [],
            "latest_terminal": None,
        },
        pr={
            "pr_number": 1191,
            "status": "OBSERVED",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "gate_policy_state": "OBSERVED",
            "check_observation_error": None,
            "base_sha": IDENTITY["base_sha"],
            "head_sha": IDENTITY["head_sha"],
        },
        required_gates=required_gates,
        leases={"active": [], "family_unavailable": [], "quarantined": []},
    )

    assert disposition == "SAFE"
    assert gate["code"] == "EXACT_HEAD_MERGE_GATE"
