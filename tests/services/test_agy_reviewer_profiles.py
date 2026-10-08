"""Contract tests for capability-aware Agy reviewer launch profiles."""

from __future__ import annotations

import pytest

from nexus.services.agy_reviewer_profiles import (
    REVIEWER_LAUNCH_CATALOG_VERSION,
    AgyReviewerProfileError,
    launch_profile_evidence,
    resolve_reviewer_launch_profile,
    supported_reviewer_models,
)


def test_catalog_exposes_only_explicit_current_reviewer_models() -> None:
    assert supported_reviewer_models() == (
        "claude-sonnet-4-6",
        "gemini-3.8-flash",
        "gemini-3.8-flash-low",
    )


def test_sonnet_profile_is_packet_only_and_does_not_emit_effort() -> None:
    profile = resolve_reviewer_launch_profile("claude-sonnet-4-6")
    evidence = launch_profile_evidence(profile)

    assert profile.mode == "plan"
    assert profile.supported_efforts == ()
    assert profile.tool_policy == "packet_only_deny_all"
    assert evidence["review_launch_catalog_version"] == REVIEWER_LAUNCH_CATALOG_VERSION
    assert evidence["review_launch_profile_id"] == "claude-sonnet-4-6.packet-review.v2"
    assert len(evidence["review_launch_profile_sha256"]) == 64
    assert evidence["review_launch_requested_effort"] is None


def test_gemini_profile_is_explicit_and_stable() -> None:
    first = resolve_reviewer_launch_profile("gemini-3.8-flash-low")
    second = resolve_reviewer_launch_profile("gemini-3.8-flash-low")

    assert first == second
    assert first.profile_sha256 == second.profile_sha256
    assert first.mode == "plan"


def test_unknown_model_fails_closed() -> None:
    with pytest.raises(AgyReviewerProfileError, match="REVIEW_MODEL_PROFILE_UNKNOWN"):
        resolve_reviewer_launch_profile("claude-future-unknown")


def test_unsupported_effort_fails_closed() -> None:
    with pytest.raises(AgyReviewerProfileError, match="REVIEW_EFFORT_UNSUPPORTED"):
        resolve_reviewer_launch_profile(
            "claude-sonnet-4-6",
            requested_effort="high",
        )


def test_gemini_flash_profile_declares_required_default_effort() -> None:
    profile = resolve_reviewer_launch_profile("gemini-3.8-flash")
    assert profile.supported_efforts == ("low", "medium", "high")
    assert getattr(profile, "default_effort", None) == "medium"
