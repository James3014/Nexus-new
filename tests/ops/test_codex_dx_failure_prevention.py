from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.ops.validate_codex_dx_failure_prevention import PreventionRegistryError, validate_registry

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "configs/codex_dx_failure_prevention.json"


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
        (lambda p: p["entries"][0]["prevention_seam"].update(path="tests/ops/no_such.py"), "does not exist"),
        (lambda p: p["entries"][0]["prevention_seam"].update(anchor="narrative explanation"), "anchor"),
        (lambda p: p["entries"][0].update(removal_condition=""), "removal"),
        (lambda p: p["entries"][0].update(failure_class="unsupported"), "unsupported"),
        (lambda p: p["entries"][0].update(extra="unknown"), "keys"),
    ],
)
def test_registry_negative_controls_fail_closed(payload: dict[str, object], mutate, message: str) -> None:
    mutate(payload)
    with pytest.raises(PreventionRegistryError, match=message):
        validate_registry(payload, root=ROOT)


def test_symlink_escape_is_rejected(payload: dict[str, object], tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("anchor", encoding="utf-8")
    link = ROOT / "tests/ops/_prevention_escape.py"
    try:
        link.symlink_to(outside)
        payload["entries"][0]["prevention_seam"].update(path="tests/ops/_prevention_escape.py", anchor="anchor")
        with pytest.raises(PreventionRegistryError, match="escapes"):
            validate_registry(payload, root=ROOT)
    finally:
        if link.is_symlink():
            link.unlink()


@pytest.mark.parametrize("ref", ["tests/ops/no_such.py#anchor", "tests/ops/test_repo_doctor.py#missing", "tests/ops/test_repo_doctor.py", "../outside.py#anchor"])
def test_evidence_reference_negative_controls_fail_closed(payload: dict[str, object], ref: str) -> None:
    payload["entries"][0]["evidence_refs"] = [ref]
    with pytest.raises(PreventionRegistryError):
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
    payload["entries"][0]["prevention_seam"]["path"] = "./tests/ops/test_bootstrap_authority_files.py"
    with pytest.raises(PreventionRegistryError, match="relative"):
        validate_registry(payload, root=ROOT)
    payload["entries"][0]["prevention_seam"]["path"] = "tests/ops/test_bootstrap_authority_files.py"
    payload["entries"][0]["summary"] = "x" * 70000
    with pytest.raises(PreventionRegistryError, match="64KiB"):
        validate_registry(payload, root=ROOT)
