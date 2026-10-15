"""Shared fixtures for the orchestrator tests."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import pytest


def reference_expected_universe_identity(contract: Mapping[str, Any]) -> str | None:
    """Test-only stand-in for Core's ``expected_universe_identity`` (#2246).

    The in-tree ``product`` package shadows nexus-core inside the pytest
    process, so in-process unit tests cannot import Core. Production resolves
    the real function through the Core transport; this copy is proven equal to
    the pinned Core by ``test_reference_universe_identity_matches_pinned_core``
    (a subprocess that runs real Core, including Core's conformance vector).
    """
    subjects = contract.get("expected_subjects")
    if not subjects:
        return None
    value = [
        contract.get("universe_generation", 0),
        [
            [
                subject["logical_subject_id"],
                subject["evidence_kind"],
                subject["requirement_mode"],
                subject["applicability"],
            ]
            for subject in sorted(subjects, key=lambda s: s["logical_subject_id"])
        ],
    ]
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@pytest.fixture
def reference_core_universe_identity(monkeypatch: pytest.MonkeyPatch):
    """Let in-process tests compute the card identity without importing Core."""
    from nexus.orchestrator import ambient_core

    monkeypatch.setattr(
        ambient_core,
        "_core_expected_universe_identity",
        lambda: reference_expected_universe_identity,
    )
    return reference_expected_universe_identity
