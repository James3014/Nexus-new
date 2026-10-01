from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.ops.validate_codex_dx_failure_prevention import (
    PreventionRegistryError,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "configs/codex_dx_failure_prevention.json"

# Sentinel for the missing-anchor negative control.
# This string MUST NOT appear in pyproject.toml (verified in the test below).
# Changing it requires updating the parametrize list that references it.
ABSENT_EVIDENCE_ANCHOR = "NEXUS_INTENTIONALLY_ABSENT_EVIDENCE_ANCHOR_ISSUE_459_V1"


def test_absent_evidence_anchor_is_not_in_pyproject_toml() -> None:
    """Guard: proves the sentinel is physically absent from pyproject.toml.

    If this test fails it means the sentinel has been accidentally introduced
    and the negative-control below must be updated.
    """
    assert ABSENT_EVIDENCE_ANCHOR not in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


@pytest.fixture
def payload() -> dict[str, object]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_canonical_registry_has_exact_bounded_coverage(payload: dict[str, object]) -> None:
    assert validate_registry(payload, root=ROOT) == 6


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p["entries"].append(copy.deepcopy(p["entries"][0])), "duplicate"),
        (lambda p: p["entries"][0].update(owner="unassigned"), "owner"),
        (
            lambda p: p["entries"][0]["prevention_seam"].update(path="tests/ops/no_such.py"),
            "does not exist",
        ),
        (
            lambda p: p["entries"][0]["prevention_seam"].update(anchor="narrative explanation"),
            "anchor",
        ),
        (lambda p: p["entries"][0].update(removal_condition=""), "removal"),
        (lambda p: p["entries"][0].update(failure_class="unsupported"), "unsupported"),
        (lambda p: p["entries"][0].update(extra="unknown"), "keys"),
    ],
)
def test_registry_negative_controls_fail_closed(
    payload: dict[str, object], mutate, message: str
) -> None:
    mutate(payload)
    with pytest.raises(PreventionRegistryError, match=message):
        validate_registry(payload, root=ROOT)


def test_symlink_escape_is_rejected(payload: dict[str, object], tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("anchor", encoding="utf-8")
    link = ROOT / "tests/ops/_prevention_escape.py"
    try:
        link.symlink_to(outside)
        payload["entries"][0]["prevention_seam"].update(
            path="tests/ops/_prevention_escape.py", anchor="anchor"
        )
        with pytest.raises(PreventionRegistryError, match="escapes"):
            validate_registry(payload, root=ROOT)
    finally:
        if link.is_symlink():
            link.unlink()


@pytest.mark.parametrize(
    "ref",
    [
        "tests/ops/no_such.py#anchor",
        f"pyproject.toml#{ABSENT_EVIDENCE_ANCHOR}",
        "tests/ops/test_repo_doctor.py",
        "../outside.py#anchor",
    ],
)
def test_evidence_reference_negative_controls_fail_closed(
    payload: dict[str, object], ref: str
) -> None:
    payload["entries"][0]["evidence_refs"] = [ref]
    with pytest.raises(PreventionRegistryError):
        validate_registry(payload, root=ROOT)


def test_missing_anchor_fails_with_intended_reason(payload: dict[str, object]) -> None:
    """Proves the replacement reference raises 'evidence anchor is not physically present'.

    This test verifies the negative control fails for the intended reason
    (missing anchor) and not for some unrelated malformed-reference error.
    """
    payload["entries"][0]["evidence_refs"] = [f"pyproject.toml#{ABSENT_EVIDENCE_ANCHOR}"]
    with pytest.raises(PreventionRegistryError, match="evidence anchor is not physically present"):
        validate_registry(payload, root=ROOT)


def test_duplicate_evidence_reference_is_rejected(payload: dict[str, object]) -> None:
    payload["entries"][1]["evidence_refs"] = payload["entries"][0]["evidence_refs"]
    with pytest.raises(PreventionRegistryError, match="duplicate evidence"):
        validate_registry(payload, root=ROOT)


def test_secret_and_authority_claims_are_rejected(payload: dict[str, object]) -> None:
    payload["entries"][0]["failure_class"] = "secret"
    with pytest.raises(PreventionRegistryError, match="unassessed"):
        validate_registry(payload, root=ROOT)
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    payload["entries"][0]["summary"] = "authorize production deployment"
    with pytest.raises(PreventionRegistryError, match="authority"):
        validate_registry(payload, root=ROOT)


def test_duplicate_physical_seam_is_rejected(payload: dict[str, object]) -> None:
    payload["entries"][1]["prevention_seam"] = payload["entries"][0]["prevention_seam"]
    with pytest.raises(PreventionRegistryError, match="duplicate"):
        validate_registry(payload, root=ROOT)


def test_alias_and_oversize_registry_fail_closed(payload: dict[str, object]) -> None:
    payload["entries"][0]["prevention_seam"]["path"] = (
        "./tests/ops/test_bootstrap_authority_files.py"
    )
    with pytest.raises(PreventionRegistryError, match="relative"):
        validate_registry(payload, root=ROOT)
    payload["entries"][0]["prevention_seam"]["path"] = "tests/ops/test_bootstrap_authority_files.py"
    payload["entries"][0]["summary"] = "x" * 70000
    with pytest.raises(PreventionRegistryError, match="64KiB"):
        validate_registry(payload, root=ROOT)
