"""Capability-aware launch profiles for bounded Agy packet reviewers.

Profiles constrain transport flags only. They do not choose a reviewer, route work,
grant tool authority, or mint acceptance/merge/release authority.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

REVIEWER_LAUNCH_CATALOG_VERSION = "nexus.agy_reviewer_launch_catalog.v1"
REVIEWER_LAUNCH_PROFILE_SCHEMA = "nexus.agy_reviewer_launch_profile.v1"


class AgyReviewerProfileError(RuntimeError):
    """Reviewer launch profile is unknown, unsupported, or internally invalid."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AgyReviewerLaunchProfile:
    profile_id: str
    model: str
    mode: str
    supported_efforts: tuple[str, ...] = ()
    tool_policy: str = "packet_only_deny_all"

    def semantic_body(self) -> dict[str, Any]:
        return {
            "schema": REVIEWER_LAUNCH_PROFILE_SCHEMA,
            "catalog_version": REVIEWER_LAUNCH_CATALOG_VERSION,
            "profile_id": self.profile_id,
            "model": self.model,
            "mode": self.mode,
            "supported_efforts": list(self.supported_efforts),
            "tool_policy": self.tool_policy,
        }

    @property
    def profile_sha256(self) -> str:
        return _sha256_json(self.semantic_body())


_PROFILES = (
    AgyReviewerLaunchProfile(
        profile_id="claude-sonnet-4-6.packet-review.v1",
        model="claude-sonnet-4-6",
        mode="accept-edits",
    ),
    AgyReviewerLaunchProfile(
        profile_id="gemini-3-8-flash.packet-review.v1",
        model="gemini-3.8-flash",
        mode="accept-edits",
    ),
    AgyReviewerLaunchProfile(
        profile_id="gemini-3-8-flash-low.packet-review.v1",
        model="gemini-3.8-flash-low",
        mode="accept-edits",
    ),
)

_PROFILES_BY_MODEL = {profile.model: profile for profile in _PROFILES}
if len(_PROFILES_BY_MODEL) != len(_PROFILES):
    raise RuntimeError("DUPLICATE_REVIEWER_MODEL_PROFILE")
if len({profile.profile_id for profile in _PROFILES}) != len(_PROFILES):
    raise RuntimeError("DUPLICATE_REVIEWER_PROFILE_ID")


def supported_reviewer_models() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES_BY_MODEL))


def resolve_reviewer_launch_profile(
    model: str | None,
    *,
    requested_effort: str | None = None,
) -> AgyReviewerLaunchProfile:
    model_name = str(model or "").strip()
    if not model_name:
        raise AgyReviewerProfileError("REVIEW_MODEL_REQUIRED")
    profile = _PROFILES_BY_MODEL.get(model_name)
    if profile is None:
        raise AgyReviewerProfileError(f"REVIEW_MODEL_PROFILE_UNKNOWN:{model_name}")

    effort = str(requested_effort or "").strip() or None
    if effort is not None and effort not in profile.supported_efforts:
        raise AgyReviewerProfileError(
            f"REVIEW_EFFORT_UNSUPPORTED:{model_name}:{effort}"
        )
    if profile.mode not in {"plan", "accept-edits"}:
        raise AgyReviewerProfileError(
            f"REVIEW_MODE_UNSUPPORTED:{model_name}:{profile.mode}"
        )
    if profile.tool_policy != "packet_only_deny_all":
        raise AgyReviewerProfileError(
            f"REVIEW_TOOL_POLICY_UNSUPPORTED:{model_name}:{profile.tool_policy}"
        )
    return profile


def launch_profile_evidence(
    profile: AgyReviewerLaunchProfile,
    *,
    requested_effort: str | None = None,
) -> dict[str, Any]:
    effort = str(requested_effort or "").strip() or None
    if effort is not None and effort not in profile.supported_efforts:
        raise AgyReviewerProfileError(
            f"REVIEW_EFFORT_UNSUPPORTED:{profile.model}:{effort}"
        )
    return {
        "review_launch_catalog_version": REVIEWER_LAUNCH_CATALOG_VERSION,
        "review_launch_profile_id": profile.profile_id,
        "review_launch_profile_sha256": profile.profile_sha256,
        "review_launch_mode": profile.mode,
        "review_launch_requested_effort": effort,
    }


__all__ = [
    "AgyReviewerLaunchProfile",
    "AgyReviewerProfileError",
    "REVIEWER_LAUNCH_CATALOG_VERSION",
    "REVIEWER_LAUNCH_PROFILE_SCHEMA",
    "launch_profile_evidence",
    "resolve_reviewer_launch_profile",
    "supported_reviewer_models",
]
