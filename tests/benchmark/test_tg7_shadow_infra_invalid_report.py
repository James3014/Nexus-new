"""Regression: run_shadow must emit a report its own validate_report accepts
when some controller-staged attempts are infra_invalid (Nexus-new #2759)."""

from __future__ import annotations

import copy
import hashlib
import os
import stat
from pathlib import Path
from typing import Any, Iterable

import pytest

from product.benchmark import _canonical, _digest
from product.benchmark.tg7_shadow import (
    ATTEMPT_RECEIPT_SCHEMA,
    PROFILE_ID,
    build_default_corpus,
    run_shadow,
    validate_corpus,
    validate_report,
    validate_shadow_receipt,
)
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION

_SELECTION_BODY = {
    "schema": "nexus.core-v1.tg7-selection.v1",
    "canonical_url": "https://github.com/bottlepy/bottle",
    "owner": "bottlepy",
    "name": "bottle",
    "commit": "62d7e076e1f7d10ed4d9e13314df32c6a1e80173",
    "tree": "4142f8e43ed54bc57bd83306cddf467f4b82f0b8",
    "snapshot_path": "repository",
    "snapshot_tree_hash": "sha256:" + "1" * 64,
    "observed_at": "2026-09-05T06:27:00Z",
    "license_spdx": "MIT",
    "license_evidence_hash": "sha256:" + "2" * 64,
    "privacy_class": "PUBLIC_OPEN_SOURCE",
    "read_only_evidence_hash": "sha256:" + "3" * 64,
    "task_set_id": "tg7-shadow-bottle-v1",
    "not_nexus_reason": "External standalone repository used only as a test fixture",
}

_TG5_BODY = {
    "receipt_schema": "nexus.certification_receipt.v1-experimental",
    "protocol_version": PUBLIC_PROTOCOL_VERSION,
    "implementation_schema": IMPLEMENTATION_SCHEMA,
    "verification": {"condition": "VALID", "reason_codes": [], "status": "VERIFIED"},
    "certification": {"disposition": "CERTIFIED"},
}


def _selection() -> dict[str, Any]:
    body = copy.deepcopy(_SELECTION_BODY)
    return {**body, "selection_hash": _digest(body)}


def _tg5() -> dict[str, Any]:
    body = copy.deepcopy(_TG5_BODY)
    return {**body, "receipt_hash": _digest(body)}


def _attempt(
    case: dict[str, Any],
    selection: dict[str, Any],
    tg5: dict[str, Any],
    material_hash: str,
    *,
    infra_reason: str | None,
) -> dict[str, Any]:
    infra = infra_reason is not None
    attempt = {
        "schema": ATTEMPT_RECEIPT_SCHEMA,
        "issuer_id": "nexus.service.v1",
        "producer_id": "nexus.controller.v1",
        "attempt_id": f"att-{case['case_id']}",
        "execution_id": f"exec-{case['case_id']}",
        "case_id": case["case_id"],
        "case_hash": case["case_hash"],
        "hostile_family": case["hostile_family"],
        "repository_commit": selection["commit"],
        "repository_tree": selection["tree"],
        "external_material_hash": material_hash,
        "canonical_request_hash": case["canonical_request_hash"],
        "oracle_hash": case["oracle_hash"],
        "oracle_source": case["oracle_source"],
        "profile_id": PROFILE_ID,
        "protocol_version": PUBLIC_PROTOCOL_VERSION,
        "implementation_schema": IMPLEMENTATION_SCHEMA,
        "tg5_receipt_hash": tg5["receipt_hash"],
        "actual_status": "INFRA_INVALID" if infra else case["expected_status"],
        "actual_disposition": "NOT_EXECUTED" if infra else case["expected_disposition"],
        "evidence_hash": "sha256:" + "e" * 64,
        "runner_result_hash": "sha256:" + "f" * 64,
        "infra_invalid": infra,
        "infra_invalid_reason": infra_reason,
        "observed_at": "2026-09-05T07:00:00Z",
    }
    attempt["attempt_hash"] = _digest(attempt)
    return attempt


def _make_writable(root: Path) -> None:
    for dirpath, _dirs, files in os.walk(root):
        os.chmod(dirpath, stat.S_IRWXU)
        for name in files:
            os.chmod(os.path.join(dirpath, name), stat.S_IRUSR | stat.S_IWUSR)


@pytest.fixture
def stage(tmp_path: Path, request: pytest.FixtureRequest):
    """Stage repository/bottle.py and read-only canonical attempts under tmp_path."""
    selection = _selection()
    tg5 = _tg5()
    corpus = build_default_corpus(selection)
    assert validate_corpus(corpus, selection=selection) == []
    repo = tmp_path / "repository"
    repo.mkdir()
    (repo / "bottle.py").write_bytes(b"# fixture bottle.py\n")
    material_hash = "sha256:" + hashlib.sha256((repo / "bottle.py").read_bytes()).hexdigest()
    attempts = tmp_path / "attempts"
    attempts.mkdir()
    request.addfinalizer(lambda: _make_writable(tmp_path))

    def _run(infra: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
        for case in corpus["cases"]:
            attempt = _attempt(
                case, selection, tg5, material_hash, infra_reason=infra.get(case["case_id"])
            )
            path = attempts / f"{case['case_id']}.json"
            path.write_bytes((_canonical(attempt) + "\n").encode("utf-8"))
            os.chmod(path, stat.S_IRUSR)
        os.chmod(attempts, stat.S_IRUSR | stat.S_IXUSR)
        return run_shadow(selection, repo, corpus, tg5)

    return selection, tg5, corpus, _run


def _infra_map(corpus: dict[str, Any], picks: Iterable[tuple[int, str]]) -> dict[str, str]:
    cases = corpus["cases"]
    return {cases[index]["case_id"]: reason for index, reason in picks}


def test_all_eligible_run_still_produces_valid_report(stage):
    selection, tg5, corpus, run = stage
    shadow, report = run({})
    total = len(corpus["cases"])
    assert validate_shadow_receipt(shadow, corpus=corpus, tg5_receipt=tg5, selection=selection) == []
    assert validate_report(report) == []
    assert validate_report(report, shadow_receipt=shadow, corpus=corpus) == []
    assert shadow["eligible_count"] == total
    assert shadow["infra_invalid_count"] == 0
    assert report["denominator"] == total


@pytest.mark.parametrize(
    "picks",
    [
        [(0, "RUNNER_UNAVAILABLE_BEFORE_EXECUTION")],
        [(3, "MATERIALIZATION_MISSING"), (40, "TIMEOUT_BEFORE_EXECUTION")],
    ],
    ids=["one_infra_invalid", "two_infra_invalid_different_families"],
)
def test_infra_invalid_attempts_produce_self_valid_report(stage, picks):
    selection, tg5, corpus, run = stage
    infra = _infra_map(corpus, picks)
    shadow, report = run(infra)
    total = len(corpus["cases"])
    eligible = total - len(infra)

    # The shadow receipt was already self-consistent before the fix.
    assert validate_shadow_receipt(shadow, corpus=corpus, tg5_receipt=tg5, selection=selection) == []
    assert shadow["eligible_count"] == eligible
    assert shadow["infra_invalid_count"] == len(infra)

    # The denominator stays the eligible count, and the report must validate.
    assert report["denominator"] == eligible
    assert validate_report(report) == []
    assert validate_report(report, shadow_receipt=shadow, corpus=corpus) == []


def test_family_count_arithmetic_is_still_enforced_with_infra_invalid(stage):
    """The fix must not simply drop the family-count arithmetic check."""
    _selection_, _tg5_, corpus, run = stage
    shadow, report = run(_infra_map(corpus, [(0, "CORRUPT_FIXTURE")]))
    assert validate_report(report, shadow_receipt=shadow, corpus=corpus) == []

    tampered = copy.deepcopy(report)
    family = corpus["cases"][-1]["hostile_family"]
    tampered["family_counts"][family] += 1
    body = {k: v for k, v in tampered.items() if k != "report_hash"}
    tampered["report_hash"] = _digest(body)
    errors = validate_report(tampered, shadow_receipt=shadow, corpus=corpus)
    assert errors, "inflated family_counts must still be rejected"
