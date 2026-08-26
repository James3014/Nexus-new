from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.learning import shared_playbook
from nexus.learning.shared_playbook import (
    KNOWN_SHARED_WORKER_PLAYBOOKS,
    PROMOTION_RECORD_FILENAME,
    SharedPlaybookError,
    inspect_shared_playbook_drift,
    load_selected_shared_playbook,
    validate_shared_playbook_candidate_intake,
)
from nexus.orchestrator.acceptance_loop import (
    CandidateAcceptanceRequest,
    IndependentReviewReceipt,
    reduce_candidate_acceptance,
)
from nexus.orchestrator.autonomy_policy import AcceptanceAuthorityKind

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RUNTIME_OVERLAY_PATH = (
    REPO_ROOT
    / "docs"
    / "reports"
    / "NEXUS_ZERO_TRUST_V2_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-22.json"
)
CANONICAL_SKILL_STATUS_REPORT_PATH = (
    REPO_ROOT
    / "docs"
    / "reports"
    / "NEXUS_ZERO_TRUST_V2_RUNTIME_SKILL_STATUS_MERGED_2026-05-22.json"
)


_G9_COMMIT = "c8c6de8c330ec8868dc515de4c337007093ad988"
_G9_TREE = "81bb0a4b81912d1a1b931e6f81bfbe9ca307b69c"
_STATE_HASH = "a" * 64
_DIFF_HASH = "b" * 64
_VERIFIED_RECEIPT_HASH = "c" * 64
_VERIFIER_ARTIFACT_HASH = "d" * 64


def _canonical_request_review(
    *,
    task_id: str,
    attempt_id: str,
    reviewer_id: str,
    implementer_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
) -> tuple[CandidateAcceptanceRequest, IndependentReviewReceipt]:
    request = CandidateAcceptanceRequest(
        task_id=task_id,
        attempt_id=attempt_id,
        implementer_id=implementer_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
        candidate_state_hash=_STATE_HASH,
        candidate_diff_hash=_DIFF_HASH,
        verified_receipt_hash=_VERIFIED_RECEIPT_HASH,
    )
    review = IndependentReviewReceipt(
        task_id=task_id,
        attempt_id=attempt_id,
        reviewer_id=reviewer_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
        candidate_state_hash=_STATE_HASH,
        candidate_diff_hash=_DIFF_HASH,
        verified_receipt_hash=_VERIFIED_RECEIPT_HASH,
        verifier_artifact_hash=_VERIFIER_ARTIFACT_HASH,
        review_status="PASS",
        exit_code=0,
        reasons=("independent G10 candidate acceptance verified",),
    )
    return request, review


def _create_canonical_acceptance_receipt(
    skill_dir: Path,
    *,
    task_id: str = "g10-diagnose-promotion-acceptance",
    attempt_id: str = "attempt-1",
    reviewer_id: str = "reviewer-independent-1",
    implementer_id: str = "worker-implementer-1",
    verdict: str | None = None,
    subject_playbook_id: str | None = "diagnose",
    manifest_sha: str | None = None,
    instructions_sha: str | None = None,
    independence_classification: str | None = AcceptanceAuthorityKind.INDEPENDENT_REVIEWER.value,
    candidate_commit_sha: str = _G9_COMMIT,
    candidate_tree_sha: str = _G9_TREE,
    binding_hash: str | None = None,
    self_promotion: bool = False,
    update_promotion_record: bool = True,
    set_active_status: bool = True,
    include_request_review: bool = True,
) -> tuple[Path, str]:
    manifest_path = skill_dir / "playbook.yaml"
    instructions_path = skill_dir / "SKILL.md"
    if set_active_status and manifest_path.is_file():
        content = manifest_path.read_text(encoding="utf-8")
        manifest_path.write_text(
            content.replace("status: CANDIDATE", "status: ACTIVE"), encoding="utf-8"
        )

    m_sha = (
        manifest_sha
        if manifest_sha is not None
        else hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    i_sha = (
        instructions_sha
        if instructions_sha is not None
        else hashlib.sha256(instructions_path.read_bytes()).hexdigest()
    )
    receipt_path = skill_dir / "acceptance_receipt.json"

    request, review = _canonical_request_review(
        task_id=task_id,
        attempt_id=attempt_id,
        reviewer_id=reviewer_id,
        implementer_id=implementer_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
    )
    result = reduce_candidate_acceptance(request, review)
    payload = result.to_dict()
    if include_request_review:
        payload["request"] = asdict(request)
        review_payload = asdict(review)
        review_payload["reasons"] = list(review.reasons)
        payload["review"] = review_payload
    if subject_playbook_id is not None:
        payload["subject_playbook_id"] = subject_playbook_id
    payload["subject_manifest_sha256"] = m_sha
    payload["subject_instructions_sha256"] = i_sha
    if independence_classification is not None:
        payload["independence_classification"] = independence_classification
    payload["self_promotion"] = self_promotion
    if verdict is not None:
        payload["verdict"] = verdict
    if binding_hash is not None:
        payload["binding_hash"] = binding_hash
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    receipt_path.write_bytes(raw_bytes)
    digest = hashlib.sha256(raw_bytes).hexdigest()

    if update_promotion_record:
        prov_path = skill_dir / PROMOTION_RECORD_FILENAME
        if prov_path.is_file():
            record = json.loads(prov_path.read_text(encoding="utf-8"))
            if set_active_status:
                record["status"] = "ACTIVE"
                record["target_manifest_sha256"] = m_sha
                record["target_instructions_sha256"] = i_sha
                record["evaluation_provenance"]["evaluated_manifest_sha256"] = m_sha
                record["evaluation_provenance"]["evaluated_instructions_sha256"] = i_sha
                record["runtime_provenance"]["integrated_manifest_sha256"] = m_sha
                record["runtime_provenance"]["integrated_instructions_sha256"] = i_sha
                record.setdefault("acceptance_decision", {})["decision"] = "PROMOTED_TO_ACTIVE"
            record.setdefault("acceptance_decision", {})["acceptance_artifact_hash"] = digest
            record["acceptance_decision"]["acceptance_receipt_path"] = (
                ".agents/skills/diagnose/acceptance_receipt.json"
            )
            record["acceptance_decision"]["acceptance_schema"] = (
                "nexus.candidate_acceptance_result.v1"
            )
            record["acceptance_decision"]["subject_manifest_sha256"] = m_sha
            record["acceptance_decision"]["subject_instructions_sha256"] = i_sha
            prov_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    return receipt_path, digest


def _copy_diagnose(tmp_path: Path, *, create_receipt: bool = False) -> Path:
    source = REPO_ROOT / ".agents" / "skills" / "diagnose"
    target = tmp_path / ".agents" / "skills" / "diagnose"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    if create_receipt:
        _create_canonical_acceptance_receipt(target, set_active_status=True)
    return target


# =========================================================================
# Witness 1: Repository-at-Rest Witness (Direct un-monkeypatched inspection)
# =========================================================================


def test_repository_at_rest_diagnose_is_candidate_and_fails_closed_without_acceptance() -> None:
    """Repository-at-Rest Witness: Directly reads candidate repository files without fixture modification.

    Proves:
    1. diagnose is at rest in CANDIDATE status with PENDING_INDEPENDENT_ACCEPTANCE.
    2. acceptance_receipt.json does not exist at rest.
    3. If status is evaluated as ACTIVE without independent acceptance, it fails closed.
    """
    manifest_path = REPO_ROOT / ".agents" / "skills" / "diagnose" / "playbook.yaml"
    prov_path = REPO_ROOT / ".agents" / "skills" / "diagnose" / "promotion_record.json"
    receipt_path = REPO_ROOT / ".agents" / "skills" / "diagnose" / "acceptance_receipt.json"

    assert manifest_path.is_file()
    assert prov_path.is_file()
    assert not receipt_path.is_file(), (
        "Candidate repository must not contain self-authored acceptance receipt"
    )

    record = json.loads(prov_path.read_text(encoding="utf-8"))
    assert record["status"] == "CANDIDATE"
    assert record["acceptance_decision"]["decision"] == "PENDING_INDEPENDENT_ACCEPTANCE"
    assert record["acceptance_decision"]["acceptance_artifact_hash"] == ""

    assert record["runtime_provenance"]["final_integration_pr"] == 577
    assert (
        record["runtime_provenance"]["final_integration_commit_sha"]
        == "c8c6de8c330ec8868dc515de4c337007093ad988"
    )
    assert (
        record["runtime_provenance"]["final_integration_tree_sha"]
        == "81bb0a4b81912d1a1b931e6f81bfbe9ca307b69c"
    )
    assert record["runtime_provenance"]["intermediate_integration_pr"] == 573

    identity = load_selected_shared_playbook("diagnose", "xray", root=REPO_ROOT, required=True)
    assert identity is not None
    assert identity.status == "CANDIDATE"
    assert identity.playbook_id == "diagnose"


# =========================================================================
# Negative Falsification Tests 1 to 15
# =========================================================================


def test_falsification_1_missing_acceptance_artifact_fails_closed(tmp_path: Path) -> None:
    """Negative Test 1: missing acceptance artifact -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    manifest = skill_dir / "playbook.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("status: CANDIDATE", "status: ACTIVE")
    )
    m_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    i_sha = hashlib.sha256((skill_dir / "SKILL.md").read_bytes()).hexdigest()
    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    rec["status"] = "ACTIVE"
    rec["target_manifest_sha256"] = m_sha
    rec["target_instructions_sha256"] = i_sha
    rec["evaluation_provenance"]["evaluated_manifest_sha256"] = m_sha
    rec["evaluation_provenance"]["evaluated_instructions_sha256"] = i_sha
    rec["runtime_provenance"]["integrated_manifest_sha256"] = m_sha
    rec["runtime_provenance"]["integrated_instructions_sha256"] = i_sha
    rec["acceptance_decision"]["decision"] = "PROMOTED_TO_ACTIVE"
    rec["acceptance_decision"]["acceptance_artifact_hash"] = "a" * 64
    prov.write_text(json.dumps(rec))

    with pytest.raises(SharedPlaybookError, match="shared_playbook_missing_independent_acceptance"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_2_missing_acceptance_artifact_hash_fails_closed(
    tmp_path: Path,
) -> None:
    """Negative Test 2: missing acceptance_artifact_hash in promotion record -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir, set_active_status=True, update_promotion_record=True
    )
    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    rec["acceptance_decision"]["acceptance_artifact_hash"] = ""  # Missing hash
    prov.write_text(json.dumps(rec))

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_missing_acceptance_artifact_hash"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_3_acceptance_artifact_hash_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    """Negative Test 3: acceptance artifact hash mismatch -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir, set_active_status=True, update_promotion_record=True
    )
    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    rec["acceptance_decision"]["acceptance_artifact_hash"] = "0" * 64  # Mismatched hash
    prov.write_text(json.dumps(rec))

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_promotion_provenance_hash_mismatch"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_4_missing_independence_classification_fails_closed(
    tmp_path: Path,
) -> None:
    """Negative Test 4: missing independence classification -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        independence_classification="",  # Missing
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_missing_independence_classification"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_5_self_asserted_independence_fails_closed(tmp_path: Path) -> None:
    """Negative Test 5: SELF_ASSERTED independence classification -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        independence_classification="SELF_ASSERTED",
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_self_promotion_forbidden"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_6_internal_implementer_independence_fails_closed(
    tmp_path: Path,
) -> None:
    """Negative Test 6: INTERNAL_IMPLEMENTER independence classification -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        independence_classification="INTERNAL_IMPLEMENTER",
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_self_promotion_forbidden"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_7_missing_subject_playbook_id_fails_closed(tmp_path: Path) -> None:
    """Negative Test 7: missing subject_playbook_id -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        subject_playbook_id="",  # Missing
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_subject_mismatch"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_8_missing_subject_manifest_hash_fails_closed(tmp_path: Path) -> None:
    """Negative Test 8: missing subject manifest hash -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        set_active_status=True,
        update_promotion_record=True,
    )
    receipt_path = skill_dir / "acceptance_receipt.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["subject_manifest_sha256"] = ""
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    receipt_path.write_bytes(raw_bytes)
    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    rec["acceptance_decision"]["acceptance_artifact_hash"] = hashlib.sha256(raw_bytes).hexdigest()
    rec["acceptance_decision"]["subject_manifest_sha256"] = ""
    prov.write_text(json.dumps(rec))

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_subject_mismatch"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_9_missing_subject_instructions_hash_fails_closed(
    tmp_path: Path,
) -> None:
    """Negative Test 9: missing subject instructions hash -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        set_active_status=True,
        update_promotion_record=True,
    )
    receipt_path = skill_dir / "acceptance_receipt.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["subject_instructions_sha256"] = ""
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    receipt_path.write_bytes(raw_bytes)
    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    rec["acceptance_decision"]["acceptance_artifact_hash"] = hashlib.sha256(raw_bytes).hexdigest()
    rec["acceptance_decision"]["subject_instructions_sha256"] = ""
    prov.write_text(json.dumps(rec))

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_subject_mismatch"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_10_arbitrary_binding_hash_fails_closed(tmp_path: Path) -> None:
    """Negative Test 10: arbitrary/non-recomputed binding_hash -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        binding_hash="whatever_arbitrary_string",  # Fake binding
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_binding_mismatch"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_11_fake_reviewer_string_fails_closed(tmp_path: Path) -> None:
    """Negative Test 11: fake reviewer string without canonical independent authority -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        reviewer_id="external-reviewer",
        include_request_review=False,
        self_promotion=False,
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_receipt_invalid"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_12_generic_pass_verdict_fails_closed(tmp_path: Path) -> None:
    """Negative Test 12: generic PASS verdict -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        verdict="PASS",  # Forbidden generic review status
        set_active_status=True,
        update_promotion_record=True,
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_verdict_invalid"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_13_stale_g8_evaluation_subject_fails_closed(tmp_path: Path) -> None:
    """Negative Test 13: stale G8 evaluation subject -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n\n## Extra Step\n", encoding="utf-8"
    )
    new_sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()

    _create_canonical_acceptance_receipt(
        skill_dir,
        instructions_sha=new_sha,
        set_active_status=True,
        update_promotion_record=True,
    )

    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    # Stale: evaluated_instructions_sha256 is set to old stale hash
    rec["evaluation_provenance"]["evaluated_instructions_sha256"] = "1" * 64
    prov.write_text(json.dumps(rec))

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_promotion_provenance_hash_mismatch"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_14_stale_g9_integration_subject_fails_closed(tmp_path: Path) -> None:
    """Negative Test 14: stale G9 integration subject -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n\n## Extra Step\n", encoding="utf-8"
    )
    new_sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()

    _create_canonical_acceptance_receipt(
        skill_dir,
        instructions_sha=new_sha,
        set_active_status=True,
        update_promotion_record=True,
    )

    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    # Stale: integrated_instructions_sha256 is set to old stale hash
    rec["runtime_provenance"]["integrated_instructions_sha256"] = "1" * 64
    prov.write_text(json.dumps(rec))

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_promotion_provenance_hash_mismatch"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_15_subject_substitution_fails_closed(tmp_path: Path) -> None:
    """Negative Test 15: subject substitution in acceptance receipt -> fail closed."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=False)
    _create_canonical_acceptance_receipt(
        skill_dir,
        set_active_status=True,
        update_promotion_record=True,
    )
    receipt_path = skill_dir / "acceptance_receipt.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["subject_instructions_sha256"] = "0" * 64
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    receipt_path.write_bytes(raw_bytes)
    prov = skill_dir / PROMOTION_RECORD_FILENAME
    rec = json.loads(prov.read_text(encoding="utf-8"))
    rec["acceptance_decision"]["acceptance_artifact_hash"] = hashlib.sha256(raw_bytes).hexdigest()
    rec["acceptance_decision"]["subject_instructions_sha256"] = "0" * 64
    prov.write_text(json.dumps(rec))

    with pytest.raises(SharedPlaybookError, match="shared_playbook_acceptance_subject_mismatch"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


# =========================================================================
# Positive Acceptance Test 16: Canonical Independent Acceptance
# =========================================================================


def test_canonical_independent_acceptance_artifact_passes_promotion(
    tmp_path: Path,
) -> None:
    """Positive Test 16: Canonical independent acceptance artifact passes promotion to ACTIVE."""
    skill_dir = _copy_diagnose(tmp_path, create_receipt=True)
    identity = load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)
    assert identity is not None
    assert identity.status == "ACTIVE"
    assert identity.playbook_id == "diagnose"
    assert identity.primary is True
    assert identity.trace_authority == "DERIVED_ONLY"
    assert identity.promotion_record_path == ".agents/skills/diagnose/promotion_record.json"

    # Verify physical provenance artifact contents
    prov_path = skill_dir / PROMOTION_RECORD_FILENAME
    assert prov_path.is_file()
    record = json.loads(prov_path.read_text(encoding="utf-8"))
    assert record["schema"] == "nexus.shared_playbook.promotion_record.v1"
    assert record["playbook_id"] == "diagnose"
    assert record["status"] == "ACTIVE"
    assert record["target_manifest_sha256"] == identity.manifest_sha256
    assert record["target_instructions_sha256"] == identity.instructions_sha256
    assert record["evaluation_provenance"]["gate"] == "G8"
    assert record["evaluation_provenance"]["verdict"] == "PASS"
    assert record["runtime_provenance"]["gate"] == "G9"
    assert record["runtime_provenance"]["fail_closed_verified"] is True
    assert record["runtime_provenance"]["final_integration_pr"] == 577
    assert (
        record["runtime_provenance"]["final_integration_commit_sha"]
        == "c8c6de8c330ec8868dc515de4c337007093ad988"
    )
    assert record["acceptance_decision"]["gate"] == "G10"
    assert record["acceptance_decision"]["decision"] == "PROMOTED_TO_ACTIVE"
    assert record["acceptance_decision"]["self_promotion"] is False

    receipt = json.loads((skill_dir / "acceptance_receipt.json").read_text(encoding="utf-8"))
    assert receipt["schema"] == "nexus.candidate_acceptance_result.v1"
    assert receipt["decision"] == "ACCEPT"
    assert (
        receipt["independence_classification"] == AcceptanceAuthorityKind.INDEPENDENT_REVIEWER.value
    )
    assert receipt["request"]["schema"] == "nexus.candidate_acceptance_request.v1"
    assert receipt["review"]["schema"] == "nexus.independent_candidate_review.v1"
    request, review = _canonical_request_review(
        task_id=receipt["task_id"],
        attempt_id=receipt["attempt_id"],
        reviewer_id=receipt["reviewer_id"],
        implementer_id=receipt["request"]["implementer_id"],
        candidate_commit_sha=receipt["candidate_commit_sha"],
        candidate_tree_sha=receipt["request"]["candidate_tree_sha"],
    )
    canonical = reduce_candidate_acceptance(request, review)
    assert canonical.decision.value == "ACCEPT"
    assert receipt["binding_hash"] == canonical.binding_hash


# =========================================================================
# F4 / F5 Default Policy Witness Tests
# =========================================================================


def test_falsification_f4_real_default_path_through_capability_planner(
    tmp_path: Path, monkeypatch
) -> None:
    """Falsification F4 / Positive Default Witness.

    Proof that without explicit skills[] injection, CapabilityPlanner and canonical policy overlay
    file physically in the repo resolve xray -> diagnose and mount ACTIVE diagnose.
    """
    assert CANONICAL_RUNTIME_OVERLAY_PATH.is_file(), "Canonical runtime policy overlay must exist"
    assert CANONICAL_SKILL_STATUS_REPORT_PATH.is_file(), "Canonical skill status report must exist"

    _copy_diagnose(tmp_path, create_receipt=True)
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    planner = CapabilityPlanner()
    # Explicit skills is None; normal canonical policy loading path via budget paths!
    plan = planner.plan(
        task_desc="Diagnose flaky test regression\n- Expected capability receipts: xray",
        task_type="bugfix",
        route={
            "selected_route": "Mode B",
            "workforce_admission_enabled": True,
            "route_decision": {"selected_capabilities": ["xray"]},
        },
        budget={
            "runtime_skill_policy_overlay_path": str(CANONICAL_RUNTIME_OVERLAY_PATH),
            "skill_status_report": str(CANONICAL_SKILL_STATUS_REPORT_PATH),
        },
        skills=None,
    )

    snapshot = plan.signal_snapshot
    contracts = snapshot.get("planned_skill_mount_contracts", [])
    violations = snapshot.get("skill_mount_violations", [])

    assert violations == []
    xray_mounts = [c for c in contracts if c.get("capability_mount") == "xray"]
    assert len(xray_mounts) == 1
    mount = xray_mounts[0]
    assert mount["skill_id"] == "diagnose"
    assert mount["capability_mount"] == "xray"
    assert mount["planner_selected_capability"] is True
    assert "shared_playbook" in mount
    sp = mount["shared_playbook"]
    assert sp["status"] == "ACTIVE"
    assert sp["primary"] is True
    assert sp["promotion_record_path"] == ".agents/skills/diagnose/promotion_record.json"


def test_falsification_f5_negative_default_control_without_xray(
    tmp_path: Path, monkeypatch
) -> None:
    """Falsification F5 / Negative Default Control.

    Without xray being selected by the route/planner, diagnose must NOT mount merely because it is ACTIVE.
    """
    assert CANONICAL_RUNTIME_OVERLAY_PATH.is_file(), "Canonical runtime policy overlay must exist"
    assert CANONICAL_SKILL_STATUS_REPORT_PATH.is_file(), "Canonical skill status report must exist"

    _copy_diagnose(tmp_path, create_receipt=True)
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    planner = CapabilityPlanner()
    # Route does NOT select xray
    plan = planner.plan(
        task_desc="Run standard codeintel query",
        task_type="refactor",
        route={
            "selected_route": "Mode B",
            "workforce_admission_enabled": True,
            "route_decision": {"selected_capabilities": ["codeintel"]},
        },
        budget={
            "runtime_skill_policy_overlay_path": str(CANONICAL_RUNTIME_OVERLAY_PATH),
            "skill_status_report": str(CANONICAL_SKILL_STATUS_REPORT_PATH),
        },
        skills=None,
    )

    snapshot = plan.signal_snapshot
    contracts = snapshot.get("planned_skill_mount_contracts", [])
    violations = snapshot.get("skill_mount_violations", [])

    assert violations == []
    # diagnose is NOT mounted
    diagnose_mounts = [
        c
        for c in contracts
        if c.get("skill_id") == "diagnose" or c.get("capability_mount") == "xray"
    ]
    assert diagnose_mounts == []


def test_unverified_shared_worker_playbooks_not_active() -> None:
    """Other candidate playbooks must NOT automatically become ACTIVE or mountable."""
    unpromoted_candidates = [
        "nexus-crash-consistency-audit",
        "nexus-bug-family-sweep",
        "nexus-proven-pattern-reuse",
        "nexus-openwiki-navigator",
        "nexus-merge-conflict-resolution",
    ]
    assert set(unpromoted_candidates).issubset(KNOWN_SHARED_WORKER_PLAYBOOKS)

    for candidate_id in unpromoted_candidates:
        with pytest.raises(SharedPlaybookError, match="shared_playbook_missing"):
            load_selected_shared_playbook(candidate_id, "xray", root=REPO_ROOT, required=True)


def test_drift_inspection_detects_upstream_instructions_drift_without_auto_mutation() -> None:
    """Upstream/reference hash drift produces re-evaluation candidate only, never mutating ACTIVE."""
    status = inspect_shared_playbook_drift(
        "diagnose",
        upstream_content="Modified upstream GPT skill instructions with new steps",
        upstream_reference_id="gpt-diagnose-v2",
        root=REPO_ROOT,
    )
    assert status.drift_detected is True
    assert status.drift_reason == "upstream_source_drift_detected"
    assert status.sync_disposition == "UPDATE_CANDIDATE_REQUIRES_EVALUATION"
    assert status.mutation_blocked is True
    assert status.status == "CANDIDATE"


def test_intake_rejects_self_promotion_to_active() -> None:
    """Intake cannot produce an ACTIVE playbook directly."""
    payload = {
        "schema": "nexus.shared_playbook.v1",
        "playbook_id": "nexus-crash-consistency-audit",
        "skill_id": "nexus-crash-consistency-audit",
        "version": "1.0.0",
        "status": "ACTIVE",
        "primary": True,
        "capability_mounts": ["xray"],
        "trace_authority": "DERIVED_ONLY",
        "permissions": {
            "filesystem": "INHERIT_ONLY",
            "network": "INHERIT_ONLY",
            "tools": "INHERIT_ONLY",
        },
        "authority": {
            "route_selection": False,
            "model_selection": False,
            "worker_selection": False,
            "approval": False,
            "integration": False,
            "merge": False,
            "promotion": False,
            "task_receipt": False,
            "claim_authority": False,
            "self_modify": False,
            "permission_expand": False,
        },
        "auto_chain": False,
        "local_transition_contract": {
            "same_task": True,
            "same_scope": True,
            "same_capability": True,
            "same_permissions": True,
            "same_authority": True,
        },
        "stages": [{"id": "audit", "exit_evidence": ["audit_log"]}],
        "transitions": [{"from": "audit", "to": "audit", "kind": "LOCAL_TRANSITION"}],
        "stop_conditions": ["complete"],
        "learning_writeback": {"mode": "CANDIDATE_ONLY", "self_modify": False},
    }
    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_intake_cannot_self_promote_active"
    ):
        validate_shared_playbook_candidate_intake(
            payload,
            skill_id="nexus-crash-consistency-audit",
            capability_mount="xray",
        )
