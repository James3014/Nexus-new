"""Test suite verifying TG-7 representative corpus, second-repo shadow, and hostile guard gates."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from product.benchmark import _digest
from product.benchmark.tg7_shadow import (
    ALLOWED_LICENSES,
    HOSTILE_FAMILIES,
    INFRA_INVALID_REASONS,
    MAXIMUM_CLAIM,
    build_default_corpus,
    run_shadow,
    validate_corpus,
    validate_report,
    validate_selection,
    validate_shadow_receipt,
    validate_tg5_receipt,
)

EVIDENCE_DIR = Path("/private/tmp/nexus-core-v1-evidence/tg7")
SELECTION_PATH = EVIDENCE_DIR / "selection.json"
TG5_PATH = EVIDENCE_DIR / "tg5-receipt.json"
CORPUS_PATH = EVIDENCE_DIR / "corpus.json"
SHADOW_RECEIPT_PATH = EVIDENCE_DIR / "shadow-receipt.json"
REPORT_PATH = EVIDENCE_DIR / "report.json"
REPO_PATH = EVIDENCE_DIR / "repository"

CANONICAL_SELECTION = {
    "schema": "nexus.core-v1.tg7-selection.v1",
    "canonical_url": "https://github.com/bottlepy/bottle",
    "owner": "bottlepy",
    "name": "bottle",
    "commit": "62d7e076e1f7d10ed4d9e13314df32c6a1e80173",
    "tree": "4142f8e43ed54bc57bd83306cddf467f4b82f0b8",
    "snapshot_path": "/private/tmp/nexus-core-v1-evidence/tg7/repository",
    "snapshot_tree_hash": "sha256:c2603ef6f90072e8f9330929d1ed794176dffee9031eeec3937c001d3ef1080b",
    "observed_at": "2026-09-05T06:27:00Z",
    "license_spdx": "MIT",
    "license_evidence_hash": "sha256:43afd5c761e9359d3111aaecf4b85a72558d5c9be035c097f8f243f4ee725c2f",
    "privacy_class": "PUBLIC_OPEN_SOURCE",
    "read_only_evidence_hash": "sha256:1870a1eba45d4e33dacbbbef9b1d87e5c46eacedfa3dbab4204ca00cbd94543c",
    "task_set_id": "tg7-shadow-bottle-v1",
    "not_nexus_reason": "External standalone Python WSGI micro-framework repository independent from Nexus-new",
    "selection_hash": "sha256:d744a17710cbce7b8ec3f339b13fd8739a909bc352f8a71bd277245e274db4c3",
}

CANONICAL_TG5 = {
    "acceptance_contract_hash": "sha256:18bb65e9224e58421c0bd57cc60ba8f1da5e2237a90d6d46567094e974247a56",
    "certification": {
        "disposition": "CERTIFIED",
        "policy": {
            "accepted": True,
            "approval_present": True,
            "authority_present": True,
            "signing_present": True,
        },
    },
    "change_set_hash": "sha256:18263cd15a306fcc58b9d7b0625b98d9b45166c01dd373d57849f9a25d7cd16b",
    "claim_ceiling": [
        "NO_MERGE_AUTHORIZATION",
        "NO_DEPLOYMENT_TRUTH",
        "NO_OUTCOME_TRUTH",
        "NO_PRODUCTION_READINESS",
        "NO_PUBLIC_PROTOCOL_STABILITY",
    ],
    "evidence_hash": "sha256:42a64047fd708624a4a8b821e7022070b38e824d78144042705d8612202bb6f6",
    "implementation_schema": "nexus.changeset_certification.v2",
    "protocol_version": "0.1.0-experimental",
    "receipt_hash": "sha256:c326b1678a2abaf0949a892ac45c7e9476ab928554e407fa5cbd43f571446d43",
    "receipt_schema": "nexus.certification_receipt.v1-experimental",
    "verification": {
        "condition": "VALID",
        "reason_codes": [],
        "status": "VERIFIED",
    },
    "verification_plan_hash": "sha256:913bf41a4af7377e9ed7cd47bc06ed1bfb0730b5eadbc89bb3a386db9bd73a61",
}


def _rehash(payload: dict[str, Any], hash_key: str) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k != hash_key}
    return {**body, hash_key: _digest(body)}


@pytest.fixture(scope="module")
def genuine_selection() -> dict[str, Any]:
    if SELECTION_PATH.exists():
        with SELECTION_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return copy.deepcopy(CANONICAL_SELECTION)


@pytest.fixture(scope="module")
def genuine_tg5() -> dict[str, Any]:
    if TG5_PATH.exists():
        with TG5_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return copy.deepcopy(CANONICAL_TG5)


@pytest.fixture(scope="module")
def genuine_corpus(genuine_selection: dict[str, Any]) -> dict[str, Any]:
    if CORPUS_PATH.exists():
        with CORPUS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return build_default_corpus(genuine_selection)


@pytest.fixture(scope="module")
def genuine_shadow_and_report(
    genuine_selection: dict[str, Any],
    genuine_corpus: dict[str, Any],
    genuine_tg5: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if SHADOW_RECEIPT_PATH.exists() and REPORT_PATH.exists():
        with SHADOW_RECEIPT_PATH.open("r", encoding="utf-8") as f:
            receipt = json.load(f)
        with REPORT_PATH.open("r", encoding="utf-8") as f:
            report = json.load(f)
        return receipt, report
    return run_shadow(genuine_selection, REPO_PATH, genuine_corpus, genuine_tg5)


@pytest.fixture(scope="module")
def genuine_shadow_receipt(
    genuine_shadow_and_report: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    return genuine_shadow_and_report[0]


@pytest.fixture(scope="module")
def genuine_report(
    genuine_shadow_and_report: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    return genuine_shadow_and_report[1]


# --- Positive Conformance Tests ---


def test_tg7_selection_manifest_conformance(genuine_selection: dict[str, Any]):
    repo_path = REPO_PATH if REPO_PATH.exists() else None
    errs = validate_selection(genuine_selection, repo_path=repo_path)
    assert errs == [], f"selection errors: {errs}"
    assert genuine_selection["license_spdx"] in ALLOWED_LICENSES
    assert genuine_selection["name"] == "bottle"
    assert genuine_selection["owner"] == "bottlepy"
    assert genuine_selection["privacy_class"] == "PUBLIC_OPEN_SOURCE"


def test_tg7_tg5_receipt_conformance(genuine_tg5: dict[str, Any]):
    errs = validate_tg5_receipt(genuine_tg5)
    assert errs == [], f"tg5 receipt errors: {errs}"
    assert genuine_tg5["verification"]["status"] == "VERIFIED"
    assert genuine_tg5["certification"]["disposition"] == "CERTIFIED"


def test_tg7_corpus_manifest_conformance(
    genuine_corpus: dict[str, Any], genuine_selection: dict[str, Any]
):
    errs = validate_corpus(genuine_corpus, selection=genuine_selection)
    assert errs == [], f"corpus errors: {errs}"
    cases = genuine_corpus["cases"]
    assert len(cases) >= 50
    counts = {fam: sum(1 for c in cases if c["hostile_family"] == fam) for fam in HOSTILE_FAMILIES}
    for fam, cnt in counts.items():
        assert cnt >= 5, f"Family {fam} count {cnt} < 5"


def test_tg7_shadow_receipt_conformance(
    genuine_shadow_receipt: dict[str, Any],
    genuine_corpus: dict[str, Any],
    genuine_tg5: dict[str, Any],
    genuine_selection: dict[str, Any],
):
    errs = validate_shadow_receipt(
        genuine_shadow_receipt,
        corpus=genuine_corpus,
        tg5_receipt=genuine_tg5,
        selection=genuine_selection,
    )
    assert errs == [], f"shadow receipt errors: {errs}"
    assert genuine_shadow_receipt["eligible_count"] >= 50
    assert genuine_shadow_receipt["infra_invalid_count"] == 0
    assert len(genuine_shadow_receipt["cases"]) == len(genuine_corpus["cases"])


def test_tg7_report_conformance_and_zero_false_cert(
    genuine_report: dict[str, Any],
    genuine_shadow_receipt: dict[str, Any],
    genuine_corpus: dict[str, Any],
):
    errs = validate_report(
        genuine_report,
        shadow_receipt=genuine_shadow_receipt,
        corpus=genuine_corpus,
    )
    assert errs == [], f"report errors: {errs}"
    assert genuine_report["false_certification_count"] == 0
    assert genuine_report["false_certification_case_ids"] == []
    assert genuine_report["denominator"] >= 50
    assert genuine_report["maximum_claim"] == MAXIMUM_CLAIM
    assert sum(genuine_report["family_counts"].values()) == genuine_report["denominator"]


# --- Negative Guard Tests (Fail-Closed) ---


def test_negative_forged_selection_and_missing_fields(
    genuine_selection: dict[str, Any],
):
    mutated = copy.deepcopy(genuine_selection)
    del mutated["canonical_url"]
    assert validate_selection(mutated) != []

    tampered = copy.deepcopy(genuine_selection)
    tampered["selection_hash"] = "sha256:" + "0" * 64
    assert any("selection_hash" in e for e in validate_selection(tampered))

    extra = copy.deepcopy(genuine_selection)
    extra["malicious_extra"] = "payload"
    assert any("unknown keys" in e for e in validate_selection(extra))


def test_negative_illegal_license_rejected(genuine_selection: dict[str, Any]):
    for bad_license in (
        "GPL-3.0",
        "AGPL-3.0",
        "Proprietary",
        "CC-BY-NC-4.0",
        "UNKNOWN",
    ):
        mutated = copy.deepcopy(genuine_selection)
        mutated["license_spdx"] = bad_license
        rehashed = _rehash(mutated, "selection_hash")
        errs = validate_selection(rehashed)
        assert any("license_spdx" in e for e in errs), f"License {bad_license} was not rejected!"


def test_negative_repository_tree_or_commit_tamper(
    genuine_selection: dict[str, Any], genuine_corpus: dict[str, Any]
):
    bad_commit_sel = copy.deepcopy(genuine_selection)
    bad_commit_sel["commit"] = "0" * 39 + "z"
    assert any("commit" in e for e in validate_selection(bad_commit_sel))

    if REPO_PATH.exists():
        bad_commit_sel2 = copy.deepcopy(genuine_selection)
        bad_commit_sel2["commit"] = "0" * 40
        rehashed_sel = _rehash(bad_commit_sel2, "selection_hash")
        assert any("commit" in e for e in validate_selection(rehashed_sel, repo_path=REPO_PATH))

    bad_corpus = copy.deepcopy(genuine_corpus)
    bad_corpus["cases"][0]["repository_tree"] = "f" * 40
    bad_corpus["cases"][0]["case_hash"] = _digest({
        k: v for k, v in bad_corpus["cases"][0].items() if k != "case_hash"
    })
    rehashed_corp = _rehash(bad_corpus, "corpus_hash")
    assert any(
        "repository_tree" in e for e in validate_corpus(rehashed_corp, selection=genuine_selection)
    )


def test_negative_missing_or_forged_oracle(
    genuine_corpus: dict[str, Any], genuine_selection: dict[str, Any]
):
    bad_corpus = copy.deepcopy(genuine_corpus)
    bad_corpus["cases"][0]["oracle_kind"] = ""
    bad_corpus["cases"][0]["case_hash"] = _digest({
        k: v for k, v in bad_corpus["cases"][0].items() if k != "case_hash"
    })
    rehashed = _rehash(bad_corpus, "corpus_hash")
    assert any("oracle_kind" in e for e in validate_corpus(rehashed, selection=genuine_selection))

    bad_corpus2 = copy.deepcopy(genuine_corpus)
    bad_corpus2["cases"][1]["oracle_hash"] = "invalid_hash_string"
    bad_corpus2["cases"][1]["case_hash"] = _digest({
        k: v for k, v in bad_corpus2["cases"][1].items() if k != "case_hash"
    })
    rehashed2 = _rehash(bad_corpus2, "corpus_hash")
    assert any("oracle_hash" in e for e in validate_corpus(rehashed2, selection=genuine_selection))


def test_negative_denominator_below_50_or_family_below_5(
    genuine_corpus: dict[str, Any], genuine_selection: dict[str, Any]
):
    bad_corpus = copy.deepcopy(genuine_corpus)
    bad_corpus["cases"] = bad_corpus["cases"][:49]
    bad_corpus["case_count"] = 49
    rehashed = _rehash(bad_corpus, "corpus_hash")
    errs = validate_corpus(rehashed, selection=genuine_selection)
    assert any("denominator must be >= 50" in e for e in errs)

    bad_corpus2 = copy.deepcopy(genuine_corpus)
    auth_cases = [c for c in bad_corpus2["cases"] if c["hostile_family"] == "AUTH_ISSUER_TAMPER"]
    other_cases = [c for c in bad_corpus2["cases"] if c["hostile_family"] != "AUTH_ISSUER_TAMPER"]
    bad_corpus2["cases"] = auth_cases[:4] + other_cases
    dummy = copy.deepcopy(other_cases[0])
    dummy["case_id"] = "tg7_dummy_case_999"
    dummy["case_hash"] = _digest({k: v for k, v in dummy.items() if k != "case_hash"})
    bad_corpus2["cases"].append(dummy)
    bad_corpus2["cases"].sort(key=lambda c: c["case_id"])
    bad_corpus2["case_count"] = len(bad_corpus2["cases"])
    rehashed2 = _rehash(bad_corpus2, "corpus_hash")
    errs2 = validate_corpus(rehashed2, selection=genuine_selection)
    assert any("AUTH_ISSUER_TAMPER has fewer than 5" in e for e in errs2)


def test_negative_forged_infra_invalid_reasons(
    genuine_shadow_receipt: dict[str, Any],
):
    bad_receipt = copy.deepcopy(genuine_shadow_receipt)
    bad_receipt["cases"][0]["infra_invalid"] = True
    bad_receipt["cases"][0]["infra_invalid_reason"] = "UNKNOWN_REASON_OR_HOSTILE_SKIP"
    bad_receipt["cases"][0]["actual_status"] = "INFRA_INVALID"
    rehashed = _rehash(bad_receipt, "receipt_hash")
    errs = validate_shadow_receipt(rehashed)
    assert any("invalid infra_invalid_reason" in e for e in errs)

    for reason in INFRA_INVALID_REASONS:
        test_r = copy.deepcopy(genuine_shadow_receipt)
        test_r["cases"][0]["infra_invalid"] = True
        test_r["cases"][0]["infra_invalid_reason"] = reason
        test_r["cases"][0]["actual_status"] = "INFRA_INVALID"
        test_r["eligible_count"] = len(test_r["cases"]) - 1
        test_r["infra_invalid_count"] = 1
        rehashed_test = _rehash(test_r, "receipt_hash")
        sub_errs = validate_shadow_receipt(rehashed_test)
        assert not any("invalid infra_invalid_reason" in e for e in sub_errs)


def test_negative_tg5_receipt_mismatch_or_stale(genuine_tg5: dict[str, Any]):
    bad_tg5 = copy.deepcopy(genuine_tg5)
    bad_tg5["verification"]["status"] = "FAILED_VERIFICATION"
    rehashed = _rehash(bad_tg5, "receipt_hash")
    assert any("status must be VERIFIED" in e for e in validate_tg5_receipt(rehashed))

    bad_tg5_2 = copy.deepcopy(genuine_tg5)
    bad_tg5_2["certification"]["disposition"] = "REJECTED"
    rehashed2 = _rehash(bad_tg5_2, "receipt_hash")
    assert any("disposition must be CERTIFIED" in e for e in validate_tg5_receipt(rehashed2))


def test_negative_false_certification_detection_fails_closed(
    genuine_report: dict[str, Any], genuine_shadow_receipt: dict[str, Any]
):
    bad_shadow = copy.deepcopy(genuine_shadow_receipt)
    bad_shadow["cases"][0]["actual_status"] = "VERIFIED"
    bad_shadow["cases"][0]["actual_disposition"] = "CERTIFIED"
    rehashed_shadow = _rehash(bad_shadow, "receipt_hash")

    bad_report = copy.deepcopy(genuine_report)
    bad_report["shadow_receipt_hash"] = rehashed_shadow["receipt_hash"]
    rehashed_report = _rehash(bad_report, "report_hash")

    errs = validate_report(rehashed_report, shadow_receipt=rehashed_shadow)
    assert any("false certification" in e.lower() for e in errs)


def test_negative_selection_cannot_be_nexus_new(
    genuine_selection: dict[str, Any],
):
    bad_sel = copy.deepcopy(genuine_selection)
    bad_sel["name"] = "Nexus-new"
    rehashed = _rehash(bad_sel, "selection_hash")
    errs = validate_selection(rehashed)
    assert any("cannot be Nexus-new" in e for e in errs)
