from __future__ import annotations

from scripts.ops.build_zero_trust_v2_replay_matrix import build_zero_trust_v2_replay_matrix


def _item(capability: str, skill_id: str) -> dict:
    return {
        "capability_id": capability,
        "skill_id": skill_id,
        "v1_evidence_count": 1,
        "risk_flags": ["requires_curation"],
        "required_next_steps": ["curate_source_repository"],
    }


def test_zero_trust_v2_replay_matrix_builds_four_arms_per_candidate() -> None:
    result = build_zero_trust_v2_replay_matrix(
        curation_backlog={"items": [_item("research_control_plane", "browserbase-fetch")]}
    )

    assert result["status"] == "PASS"
    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["row_count"] == 4
    assert result["summary"]["arms_per_candidate"] == 4
    assert result["summary"]["promotion_credit_source"] == "v2_only"
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["summary"]["public_benchmark_allowed"] is False
    assert {row["arm_type"] for row in result["rows"]} == {
        "capability_only_v2",
        "candidate_skill_v2",
        "wrong_or_quarantined_skill_v2",
        "shadow_candidate_v2",
    }


def test_zero_trust_v2_replay_matrix_rows_are_schema_v2_and_v1_context_only() -> None:
    result = build_zero_trust_v2_replay_matrix(curation_backlog={"items": [_item("codeintel", "code-skill")]})

    for row in result["rows"]:
        assert row["security_contract_version"] == "v2"
        assert row["promotion_credit_source"] == "v2_only"
        assert row["v1_context_only"] is True
        assert row["v1_evidence_count"] == 1
        assert row["v2_evidence_count"] == 0
        assert row["requires_sandbox_attestation"] is True
        assert row["requires_runtime_signed_receipt"] is True
        assert row["requires_clean_slate_isolation"] is True
        assert row["shadow_output_affects_runtime"] is False


def test_zero_trust_v2_replay_matrix_wrong_skill_arm_is_expected_blocked() -> None:
    result = build_zero_trust_v2_replay_matrix(curation_backlog={"items": [_item("xray", "xray-skill")]})

    by_arm = {row["arm_type"]: row for row in result["rows"]}
    assert by_arm["capability_only_v2"]["skill_id"] == ""
    assert by_arm["capability_only_v2"]["expected_status"] == "BASELINE"
    assert by_arm["wrong_or_quarantined_skill_v2"]["skill_id"] == "xray-skill"
    assert by_arm["wrong_or_quarantined_skill_v2"]["expected_status"] == "BLOCKED_BY_POLICY"
