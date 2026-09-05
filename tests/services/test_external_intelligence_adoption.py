from __future__ import annotations

import base64
import hashlib
import json

import pytest

from nexus.contracts.lifecycle_action import (
    LifecycleActionType,
    parse_external_adoption_task_card,
)
from nexus.services.external_intelligence_adoption import (
    ExternalIntelligenceAdoptionError,
    build_external_adoption_validation,
    build_external_candidate_adoption_request,
    build_external_settlement_handoff,
)
from nexus.services.external_intelligence_closure import CLAIM_CEILING


def _current_eia_card(*, allow_deletions: bool = False) -> bytes:
    deletion_line = f"- allow_deletions: {'true' if allow_deletions else 'false'}\n"
    return (
        "# Task Card\n\n"
        "## Identity\n\n"
        "- task_id: `task-1`\n"
        "- status: ACTIVE\n"
        "- AUTO_CHAIN: false\n"
        + deletion_line
        + "\n"
        "## Allowed files\n\n"
        "- `src/a.py`\n"
        "- `tests/test_a.py`\n\n"
        "## Forbidden scope\n\n"
        "No writes to `tasks/**`; no merge or release authority.\n\n"
        "## Verification commands\n\n"
        "```bash\n"
        "python3 -m pytest -q tests/test_a.py\n"
        "git diff --check\n"
        "```\n"
    ).encode("utf-8")


def _historical_epb_card() -> bytes:
    return (
        "# Task Card\n\n"
        "task_id: `task-1`\n\n"
        "`AUTO_CHAIN=false`\n\n"
        "## Allowed repository paths\n\n"
        "- `src/a.py`\n\n"
        "## Forbidden scope\n\n"
        "- `tasks/**`\n\n"
        "## Exact verification commands\n\n"
        "- `git diff --check`\n"
    ).encode("utf-8")


def _closure(card: bytes) -> dict:
    card_hash = hashlib.sha256(card).hexdigest()
    candidate = {
        "schema": "external_intelligence_task_candidate.v1",
        "task_id": "task-1",
        "base_sha": "a" * 40,
        "workspace_id": "workspace-1",
        "workspace_path": "/tmp/workspace-1",
        "candidate_commit": "1" * 40,
        "candidate_tree": "2" * 40,
        "candidate_diff_sha256": "3" * 64,
        "changed_paths": ["src/a.py"],
        "deleted_paths": [],
        "composition_order": ["u1"],
        "unit_lineage": [],
        "claim_ceiling": "TASK_CANDIDATE_REQUIRES_WHOLE_TASK_VERIFICATION",
        "task_candidate_id": "task-candidate-1",
    }
    whole = {
        "schema": "external_intelligence_whole_task_verification.v1",
        "status": "PASS",
        "task_id": "task-1",
        "task_candidate_id": "task-candidate-1",
        "verification_id": "whole-verification-1",
        "results": [],
    }
    packet = {
        "schema": "external_intelligence_acceptance_packet.v1",
        "task_id": "task-1",
        "task_card_ref": "tasks/x.md",
        "task_card_hash": card_hash,
        "external_intelligence_refs": ["receipt-1"],
        "task_candidate": {
            "task_candidate_id": "task-candidate-1",
            "base_sha": "a" * 40,
            "candidate_commit": "1" * 40,
            "candidate_tree": "2" * 40,
            "candidate_diff_sha256": "3" * 64,
            "changed_paths": ["src/a.py"],
            "deleted_paths": [],
            "composition_order": ["u1"],
        },
        "unit_lineage": [],
        "whole_task_verification_id": "whole-verification-1",
        "whole_task_status": "PASS",
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "claim_ceiling": CLAIM_CEILING,
        "packet_id": "packet-1",
    }
    capsule = {
        "schema": "external_intelligence_closure_capsule.v1",
        "task_id": "task-1",
        "candidate_commit": "1" * 40,
        "candidate_tree": "2" * 40,
        "candidate_diff_sha256": "3" * 64,
        "verification_state": "WHOLE_TASK_PASS",
        "acceptance_packet_ref": "state/acceptance.json",
        "acceptance_packet_sha256": "4" * 64,
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "next_action": "run_independent_candidate_acceptance_audit",
        "stop_if": "independent_acceptance_not_explicitly_granted",
        "claim_ceiling": CLAIM_CEILING,
        "capsule_id": "capsule-1",
    }
    return {
        "schema": "external_intelligence_closure_run.v1",
        "status": CLAIM_CEILING,
        "task_id": "task-1",
        "task_candidate": candidate,
        "whole_verification": whole,
        "unit_verifications": [],
        "repair_deltas": [],
        "acceptance_packet": packet,
        "control_capsule": capsule,
        "telemetry": {},
        "claim_ceiling": CLAIM_CEILING,
        "run_id": "5" * 64,
    }


def _acceptance_bytes(validation_sha: str, **overrides) -> bytes:
    payload = {
        "schema": "nexus.external_candidate_acceptance.v1",
        "task_id": "task-1",
        "candidate_commit_sha": "1" * 40,
        "candidate_tree_sha": "2" * 40,
        "candidate_diff_sha256": "3" * 64,
        "validation_receipt_sha256": validation_sha,
        "reviewer_id": "independent-reviewer",
        "disposition": "ACCEPT_CANDIDATE",
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_external_adoption_task_card_parser_accepts_historical_and_current_eia_shapes():
    historical = parse_external_adoption_task_card(_historical_epb_card())
    current = parse_external_adoption_task_card(_current_eia_card())

    assert historical.allowed_repository_paths == ("src/a.py",)
    assert historical.exact_verification_commands == ("git diff --check",)
    assert current.allowed_repository_paths == ("src/a.py", "tests/test_a.py")
    assert current.exact_verification_commands == (
        "python3 -m pytest -q tests/test_a.py",
        "git diff --check",
    )
    assert current.forbidden_repository_patterns == ("tasks/**",)
    assert current.auto_chain is False


def test_closure_builds_non_accepting_settlement_handoff_for_single_existing_adoption_authority():
    card = _current_eia_card()
    closure = _closure(card)

    validation = build_external_adoption_validation(
        repository="James3014/Nexus-new", closure=closure, task_card_bytes=card
    )
    handoff = build_external_settlement_handoff(
        repository="James3014/Nexus-new", closure=closure, task_card_bytes=card
    )

    assert hashlib.sha256(validation.json_bytes).hexdigest() == validation.sha256
    assert json.loads(base64.b64decode(validation.b64)) == validation.payload
    assert handoff["validation_receipt_sha256"] == validation.sha256
    assert handoff["next_action"] == "nexus_candidate_adopt_external"
    assert handoff["required_acceptance_schema"] == "nexus.external_candidate_acceptance.v1"
    assert handoff["independent_acceptance_required"] is True
    assert handoff["automatic_adoption_performed"] is False
    assert handoff["approval_performed"] is False
    assert handoff["integration_performed"] is False
    assert handoff["claim_ceiling"] == CLAIM_CEILING


def test_independent_acceptance_builds_existing_closed_adoption_request_without_settling_it():
    card = _current_eia_card()
    closure = _closure(card)
    validation = build_external_adoption_validation(
        repository="James3014/Nexus-new", closure=closure, task_card_bytes=card
    )
    acceptance = _acceptance_bytes(validation.sha256)

    request = build_external_candidate_adoption_request(
        repository="James3014/Nexus-new",
        closure=closure,
        task_card_bytes=card,
        independent_acceptance_bytes=acceptance,
        controller_revision="b" * 40,
        tool_manifest_hash="c" * 64,
        full_tool_schema_hash="d" * 64,
        permission_policy_hash="e" * 64,
        lifecycle_revision="nexus.lifecycle.gateway.v2",
        server_instance_id="server-1",
    )
    repeated = build_external_candidate_adoption_request(
        repository="James3014/Nexus-new",
        closure=closure,
        task_card_bytes=card,
        independent_acceptance_bytes=acceptance,
        controller_revision="b" * 40,
        tool_manifest_hash="c" * 64,
        full_tool_schema_hash="d" * 64,
        permission_policy_hash="e" * 64,
        lifecycle_revision="nexus.lifecycle.gateway.v2",
        server_instance_id="server-1",
    )

    assert request.schema == "nexus.external_candidate_adoption_request.v1"
    assert request.candidate_commit_sha == "1" * 40
    assert request.allowed_files == ("src/a.py", "tests/test_a.py")
    assert request.verifier_commands == (
        "python3 -m pytest -q tests/test_a.py",
        "git diff --check",
    )
    assert request.action.action_type is LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL
    assert request.action.allowed_paths == request.allowed_files
    assert request.semantic_hash() == repeated.semantic_hash()
    assert request.attempt_id == repeated.attempt_id
    assert request.action_id == repeated.action_id
    assert request.idempotency_key == repeated.idempotency_key


def test_bridge_rejects_missing_or_mismatched_independent_acceptance():
    card = _current_eia_card()
    closure = _closure(card)
    validation = build_external_adoption_validation(
        repository="James3014/Nexus-new", closure=closure, task_card_bytes=card
    )
    kwargs = dict(
        repository="James3014/Nexus-new",
        closure=closure,
        task_card_bytes=card,
        controller_revision="b" * 40,
        tool_manifest_hash="c" * 64,
        full_tool_schema_hash="d" * 64,
        permission_policy_hash="e" * 64,
        lifecycle_revision="nexus.lifecycle.gateway.v2",
        server_instance_id="server-1",
    )

    with pytest.raises(ExternalIntelligenceAdoptionError, match="INDEPENDENT_ACCEPTANCE_BYTES_REQUIRED"):
        build_external_candidate_adoption_request(
            **kwargs, independent_acceptance_bytes=b""
        )
    with pytest.raises(ExternalIntelligenceAdoptionError, match="INDEPENDENT_ACCEPTANCE_BINDING_MISMATCH"):
        build_external_candidate_adoption_request(
            **kwargs,
            independent_acceptance_bytes=_acceptance_bytes(
                validation.sha256, candidate_commit_sha="9" * 40
            ),
        )
    with pytest.raises(ExternalIntelligenceAdoptionError, match="INDEPENDENT_ACCEPTANCE_BINDING_MISMATCH"):
        build_external_candidate_adoption_request(
            **kwargs,
            independent_acceptance_bytes=_acceptance_bytes(
                validation.sha256, disposition="REJECT_CANDIDATE"
            ),
        )


def test_bridge_rejects_claim_widening_card_drift_and_unauthorized_deletion():
    card = _current_eia_card()
    closure = _closure(card)

    widened = dict(closure)
    widened["status"] = "ACCEPTED"
    with pytest.raises(ExternalIntelligenceAdoptionError, match="CLOSURE_NOT_READY_FOR_INDEPENDENT_ACCEPTANCE"):
        build_external_adoption_validation(
            repository="James3014/Nexus-new", closure=widened, task_card_bytes=card
        )

    with pytest.raises(ExternalIntelligenceAdoptionError, match="TASK_CARD_HASH_MISMATCH"):
        build_external_adoption_validation(
            repository="James3014/Nexus-new",
            closure=closure,
            task_card_bytes=card + b"\n",
        )

    deletion = _closure(card)
    deletion_candidate = dict(deletion["task_candidate"])
    deletion_candidate["deleted_paths"] = ["src/a.py"]
    deletion["task_candidate"] = deletion_candidate
    deletion_packet = dict(deletion["acceptance_packet"])
    deletion_packet_candidate = dict(deletion_packet["task_candidate"])
    deletion_packet_candidate["deleted_paths"] = ["src/a.py"]
    deletion_packet["task_candidate"] = deletion_packet_candidate
    deletion["acceptance_packet"] = deletion_packet
    with pytest.raises(ExternalIntelligenceAdoptionError, match="CANDIDATE_DELETION_NOT_AUTHORIZED"):
        build_external_adoption_validation(
            repository="James3014/Nexus-new", closure=deletion, task_card_bytes=card
        )


def test_bridge_preserves_explicit_eia_deletion_authority_into_existing_adoption_request():
    card = _current_eia_card(allow_deletions=True)
    closure = _closure(card)
    candidate = dict(closure["task_candidate"])
    candidate["deleted_paths"] = ["src/a.py"]
    closure["task_candidate"] = candidate
    packet = dict(closure["acceptance_packet"])
    packet_candidate = dict(packet["task_candidate"])
    packet_candidate["deleted_paths"] = ["src/a.py"]
    packet["task_candidate"] = packet_candidate
    closure["acceptance_packet"] = packet

    validation = build_external_adoption_validation(
        repository="James3014/Nexus-new", closure=closure, task_card_bytes=card
    )
    acceptance = _acceptance_bytes(validation.sha256)
    request = build_external_candidate_adoption_request(
        repository="James3014/Nexus-new",
        closure=closure,
        task_card_bytes=card,
        independent_acceptance_bytes=acceptance,
        controller_revision="b" * 40,
        tool_manifest_hash="c" * 64,
        full_tool_schema_hash="d" * 64,
        permission_policy_hash="e" * 64,
        lifecycle_revision="nexus.lifecycle.gateway.v2",
        server_instance_id="server-1",
    )

    assert request.authorized_deletions == ("src/a.py",)
    assert request.action.allowed_paths == request.allowed_files
