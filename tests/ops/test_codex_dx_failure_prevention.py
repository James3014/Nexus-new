from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.ops.validate_codex_dx_failure_prevention import (
    PreventionRegistryError,
    _validate_evidence_semantics,
    validate_registry,
)

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
        (lambda p: p["entries"][0]["prevention_seam"].update(path="tests/ops/no_such.py"), "exist"),
        (
            lambda p: p["entries"][0]["prevention_seam"].update(anchor="a narrative explanation"),
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
    ("ref", "message"),
    [
        ("tests/ops/no_such.py#anchor", "exist"),
        ("tests/ops/test_repo_doctor.py#no_such_anchor", "anchor"),
        ("tests/ops/test_repo_doctor.py", "path#anchor"),
        ("../outside.py#anchor", "aliased|escapes"),
    ],
)
def test_evidence_reference_negative_controls(
    payload: dict[str, object], ref: str, message: str
) -> None:
    payload["entries"][0]["evidence_refs"] = [ref]
    with pytest.raises(PreventionRegistryError, match=message):
        validate_registry(payload, root=ROOT)


def test_duplicate_evidence_reference_is_rejected(payload: dict[str, object]) -> None:
    payload["entries"][1]["evidence_refs"] = payload["entries"][0]["evidence_refs"]
    with pytest.raises(PreventionRegistryError, match="duplicate evidence"):
        validate_registry(payload, root=ROOT)


def test_semantic_duplicate_is_rejected(payload: dict[str, object]) -> None:
    payload["entries"][1]["summary"] = payload["entries"][0]["summary"].upper()
    with pytest.raises(PreventionRegistryError, match="semantic"):
        validate_registry(payload, root=ROOT)


def test_secret_cannot_be_admitted(payload: dict[str, object]) -> None:
    payload["entries"][0]["failure_class"] = "secret"
    with pytest.raises(PreventionRegistryError, match="unassessed"):
        validate_registry(payload, root=ROOT)


def test_duplicate_physical_seam_is_rejected(payload: dict[str, object]) -> None:
    payload["entries"][1]["prevention_seam"] = payload["entries"][0]["prevention_seam"]
    with pytest.raises(PreventionRegistryError, match="duplicate prevention seam"):
        validate_registry(payload, root=ROOT)


def test_one_character_anchor_is_not_a_physical_identifier(payload: dict[str, object]) -> None:
    payload["entries"][0]["prevention_seam"]["anchor"] = "e"
    with pytest.raises(PreventionRegistryError, match="exact Python"):
        validate_registry(payload, root=ROOT)


def test_alias_path_and_oversize_registry_fail_closed(payload: dict[str, object]) -> None:
    payload["entries"][0]["prevention_seam"]["path"] = "./tests/ops/test_repo_doctor.py"
    with pytest.raises(PreventionRegistryError, match="relative"):
        validate_registry(payload, root=ROOT)
    payload["entries"][0]["prevention_seam"]["path"] = "tests/ops/test_repo_doctor.py"
    payload["entries"][0]["summary"] = "x" * 70000
    with pytest.raises(PreventionRegistryError, match="64KiB"):
        validate_registry(payload, root=ROOT)


def test_evidence_alias_and_reference_count_fail_closed(payload: dict[str, object]) -> None:
    payload["entries"][0]["evidence_refs"] = [
        "configs/benchmarks/../benchmarks/codex_dx_before_v1.json#before-setup-1"
    ]
    with pytest.raises(PreventionRegistryError, match="aliased"):
        validate_registry(payload, root=ROOT)

    payload["entries"][0]["evidence_refs"] = [
        f"configs/benchmarks/codex_dx_before_v1.json#before-setup-{index}" for index in range(1, 5)
    ]
    with pytest.raises(PreventionRegistryError, match="bounded"):
        validate_registry(payload, root=ROOT)


def test_duplicate_entry_id_is_independent_of_evidence_ids(payload: dict[str, object]) -> None:
    duplicate = copy.deepcopy(payload["entries"][0])
    duplicate["failure_class"] = payload["entries"][1]["failure_class"]
    duplicate["summary"] = "A different summary"
    duplicate["evidence_refs"] = payload["entries"][1]["evidence_refs"]
    duplicate["prevention_seam"] = payload["entries"][1]["prevention_seam"]
    payload["entries"][1] = duplicate
    with pytest.raises(PreventionRegistryError, match="duplicate entry id"):
        validate_registry(payload, root=ROOT)


def test_cross_session_evidence_spoof_is_rejected() -> None:
    source = json.loads(
        (ROOT / "configs/benchmarks/codex_dx_before_v1.json").read_text(encoding="utf-8")
    )
    trial = next(item for item in source["trials"] if item["trial_id"] == "before-verification-1")
    trial["session_id"] = "codex-exec-luna-before-2"

    with pytest.raises(PreventionRegistryError, match="artifact identity"):
        _validate_evidence_semantics("convention", source, "before-verification-1")
