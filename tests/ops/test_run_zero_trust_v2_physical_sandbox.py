from __future__ import annotations

from scripts.ops.run_zero_trust_v2_physical_sandbox import run_zero_trust_v2_physical_sandbox_matrix


def _row(arm_type: str) -> dict:
    return {
        "row_id": f"row-{arm_type}",
        "capability_id": "codeintel",
        "skill_id": "code-skill",
        "source_skill_id": "code-skill",
        "arm_type": arm_type,
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
    }


def test_zero_trust_v2_physical_sandbox_matrix_is_runtime_non_mutating() -> None:
    result = run_zero_trust_v2_physical_sandbox_matrix(
        replay_matrix={"rows": [_row("capability_only_v2"), _row("wrong_or_quarantined_skill_v2")]},
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        limit=2,
    )

    assert result["status"] == "PASS"
    assert result["summary"]["executed_row_count"] == 2
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["summary"]["automatic_apply_allowed"] is False
    assert result["summary"]["public_benchmark_allowed"] is False
    assert result["summary"]["probe_only"] is True
    assert result["summary"]["execution_status_counts"] == {"BASELINE_ONLY": 1, "BLOCKED_BY_POLICY": 1}


def test_build_probe_validates_the_attestation_with_the_runner_secret(monkeypatch) -> None:
    """#3229: the report builder hands the signing secret to the validator, so a report
    cannot say PASS for an attestation whose signature was never checked."""
    from scripts.ops import build_zero_trust_v2_sandbox_probe as build

    attestation = {"sandbox_mode": "seatbelt", "artifact_hash": "a" * 64}
    probe = {"status": "PASS", "promotion_eligible": True, "sandbox_attestation": attestation}
    seen: dict[str, object] = {}

    def fake_probe(command, *, signing_secret):
        seen["probe_secret"] = signing_secret
        return probe

    def fake_validate(candidate, *, signing_secret=None):
        seen["validated"] = candidate
        seen["validate_secret"] = signing_secret
        return {"status": "PASS", "reasons": []}

    monkeypatch.setattr(build, "run_macos_sandbox_probe", fake_probe)
    monkeypatch.setattr(build, "validate_sandbox_attestation", fake_validate)
    report = build.build_zero_trust_v2_sandbox_probe(
        command=["/bin/echo", "ok"], signing_secret="s-3229"
    )
    assert seen == {"probe_secret": "s-3229", "validated": attestation, "validate_secret": "s-3229"}
    assert report["summary"]["promotion_eligible"] is True
    assert report["summary"]["attestation_validation_status"] == "PASS"
