"""Negative guard tests and controller acceptance validation for TG-7 shadow."""

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
    MAXIMUM_CLAIM,
    build_default_corpus,
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

# Isolated synthetic constants strictly for SELF_TEST fixtures (cannot satisfy acceptance path)
SELF_TEST_SYNTHETIC_SELECTION = {
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

SELF_TEST_SYNTHETIC_TG5 = {
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


# --- Self-Test Fixtures (Only for schema unit tests and negative controls) ---


@pytest.fixture(scope="module")
def self_test_selection() -> dict[str, Any]:
    return copy.deepcopy(SELF_TEST_SYNTHETIC_SELECTION)


@pytest.fixture(scope="module")
def self_test_tg5() -> dict[str, Any]:
    return copy.deepcopy(SELF_TEST_SYNTHETIC_TG5)


@pytest.fixture(scope="module")
def self_test_corpus(self_test_selection: dict[str, Any]) -> dict[str, Any]:
    return build_default_corpus(self_test_selection)


# --- Negative Guard Tests (Fail-Closed) ---


def test_negative_forged_selection_and_missing_fields(
    self_test_selection: dict[str, Any],
):
    mutated = copy.deepcopy(self_test_selection)
    del mutated["canonical_url"]
    assert validate_selection(mutated) != []

    tampered = copy.deepcopy(self_test_selection)
    tampered["selection_hash"] = "sha256:" + "0" * 64
    assert any("selection_hash" in e for e in validate_selection(tampered))

    extra = copy.deepcopy(self_test_selection)
    extra["malicious_extra"] = "payload"
    assert any("unknown keys" in e for e in validate_selection(extra))


def test_negative_illegal_license_rejected(self_test_selection: dict[str, Any]):
    for bad_license in (
        "GPL-3.0",
        "AGPL-3.0",
        "Proprietary",
        "CC-BY-NC-4.0",
        "UNKNOWN",
    ):
        mutated = copy.deepcopy(self_test_selection)
        mutated["license_spdx"] = bad_license
        rehashed = _rehash(mutated, "selection_hash")
        errs = validate_selection(rehashed)
        assert any("license_spdx" in e for e in errs), f"License {bad_license} was not rejected!"


def test_negative_repository_tree_or_commit_tamper(
    self_test_selection: dict[str, Any], self_test_corpus: dict[str, Any]
):
    bad_commit_sel = copy.deepcopy(self_test_selection)
    bad_commit_sel["commit"] = "0" * 40
    bad_commit_sel = _rehash(bad_commit_sel, "selection_hash")
    errs = validate_corpus(self_test_corpus, selection=bad_commit_sel)
    assert any("commit mismatch" in e for e in errs)

    bad_tree_sel = copy.deepcopy(self_test_selection)
    bad_tree_sel["tree"] = "0" * 40
    bad_tree_sel = _rehash(bad_tree_sel, "selection_hash")
    errs = validate_corpus(self_test_corpus, selection=bad_tree_sel)
    assert any("tree mismatch" in e for e in errs)


def test_negative_missing_or_forged_oracle(
    self_test_selection: dict[str, Any], self_test_corpus: dict[str, Any]
):
    tampered_corpus = copy.deepcopy(self_test_corpus)
    tampered_corpus["cases"][0]["oracle_hash"] = "sha256:" + "f" * 64
    tampered_corpus = _rehash(tampered_corpus, "corpus_hash")
    errs = validate_corpus(tampered_corpus, selection=self_test_selection)
    assert any("oracle_hash" in e for e in errs)


def test_negative_denominator_below_50_or_family_below_5(
    self_test_selection: dict[str, Any], self_test_corpus: dict[str, Any]
):
    truncated = copy.deepcopy(self_test_corpus)
    truncated["cases"] = truncated["cases"][:40]
    truncated["case_count"] = 40
    truncated = _rehash(truncated, "corpus_hash")
    errs = validate_corpus(truncated, selection=self_test_selection)
    assert any(">= 50" in e for e in errs)

    skewed = copy.deepcopy(self_test_corpus)
    skewed["cases"] = [c for c in skewed["cases"] if c["hostile_family"] != "AUTH_ISSUER_TAMPER"]
    skewed["case_count"] = len(skewed["cases"])
    skewed = _rehash(skewed, "corpus_hash")
    errs = validate_corpus(skewed, selection=self_test_selection)
    assert any("AUTH_ISSUER_TAMPER" in e for e in errs)


def test_negative_forged_infra_invalid_reasons(
    self_test_selection: dict[str, Any],
    self_test_corpus: dict[str, Any],
    self_test_tg5: dict[str, Any],
):
    fake_receipt = {
        "schema": "nexus.core-v1.tg7-shadow-receipt.v1",
        "run_id": "test-run",
        "tg5_receipt_hash": self_test_tg5["receipt_hash"],
        "selection_hash": self_test_selection["selection_hash"],
        "corpus_hash": self_test_corpus["corpus_hash"],
        "task_set_id": "tg7-shadow-bottle-v1",
        "repository": {
            "owner": self_test_selection["owner"],
            "name": self_test_selection["name"],
            "commit": self_test_selection["commit"],
            "tree": self_test_selection["tree"],
        },
        "eligible_count": len(self_test_corpus["cases"]) - 1,
        "infra_invalid_count": 1,
        "cases": [
            {
                "case_id": self_test_corpus["cases"][0]["case_id"],
                "hostile_family": self_test_corpus["cases"][0]["hostile_family"],
                "attempt_id": "att-1",
                "attempt_hash": "sha256:" + "a" * 64,
                "oracle_hash": self_test_corpus["cases"][0]["oracle_hash"],
                "result_hash": "sha256:" + "b" * 64,
                "actual_status": "INFRA_INVALID",
                "actual_disposition": "BLOCKED",
                "evidence_hash": "sha256:" + "c" * 64,
                "infra_invalid": True,
                "infra_invalid_reason": "UNAUTHORIZED_FORGED_REASON",
            }
        ]
        + [
            {
                "case_id": c["case_id"],
                "hostile_family": c["hostile_family"],
                "attempt_id": f"att-{i}",
                "attempt_hash": "sha256:" + "a" * 64,
                "oracle_hash": c["oracle_hash"],
                "result_hash": "sha256:" + "b" * 64,
                "actual_status": c["expected_status"],
                "actual_disposition": c["expected_disposition"],
                "evidence_hash": "sha256:" + "c" * 64,
                "infra_invalid": False,
                "infra_invalid_reason": None,
            }
            for i, c in enumerate(self_test_corpus["cases"][1:])
        ],
    }
    fake_receipt = _rehash(fake_receipt, "receipt_hash")
    errs = validate_shadow_receipt(
        fake_receipt,
        corpus=self_test_corpus,
        tg5_receipt=self_test_tg5,
        selection=self_test_selection,
    )
    assert any("UNAUTHORIZED_FORGED_REASON" in e for e in errs)


def test_negative_tg5_receipt_mismatch_or_stale(
    self_test_selection: dict[str, Any],
    self_test_corpus: dict[str, Any],
    self_test_tg5: dict[str, Any],
):
    bad_tg5 = copy.deepcopy(self_test_tg5)
    bad_tg5["verification"]["status"] = "UNVERIFIABLE"
    bad_tg5 = _rehash(bad_tg5, "receipt_hash")
    errs = validate_tg5_receipt(bad_tg5)
    assert any("VERIFIED" in e for e in errs)


def test_negative_false_certification_detection_fails_closed(
    self_test_selection: dict[str, Any],
    self_test_corpus: dict[str, Any],
    self_test_tg5: dict[str, Any],
):
    bad_report = {
        "schema": "nexus.core-v1.tg7-report.v1",
        "task_set_id": "tg7-shadow-bottle-v1",
        "shadow_receipt_hash": "sha256:" + "a" * 64,
        "selection_hash": self_test_selection["selection_hash"],
        "tg5_receipt_hash": self_test_tg5["receipt_hash"],
        "generated_at": "2026-09-05T06:45:00Z",
        "denominator": len(self_test_corpus["cases"]),
        "eligible_count": len(self_test_corpus["cases"]),
        "infra_invalid_count": 0,
        "family_counts": {fam: 7 for fam in HOSTILE_FAMILIES},
        "false_certification_count": 1,
        "false_certification_case_ids": [self_test_corpus["cases"][0]["case_id"]],
        "trust_mismatches": 0,
        "maximum_claim": MAXIMUM_CLAIM,
    }
    bad_report = _rehash(bad_report, "report_hash")
    errs = validate_report(bad_report, corpus=self_test_corpus)
    assert any("HIGH RISK FALSE CERTIFICATION" in e for e in errs)


def test_negative_selection_cannot_be_nexus_new(
    self_test_selection: dict[str, Any],
):
    bad_sel = copy.deepcopy(self_test_selection)
    bad_sel["name"] = "Nexus-new"
    bad_sel = _rehash(bad_sel, "selection_hash")
    errs = validate_selection(bad_sel)
    assert any("Nexus-new" in e for e in errs)


# ==============================================================================
# Controller Physical Acceptance Tests (Zero Synthetic Fallback)
# ==============================================================================


def _has_controller_evidence() -> bool:
    return (
        SELECTION_PATH.is_file()
        and TG5_PATH.is_file()
        and CORPUS_PATH.is_file()
        and SHADOW_RECEIPT_PATH.is_file()
        and REPORT_PATH.is_file()
        and REPO_PATH.is_dir()
    )


if _has_controller_evidence():

    @pytest.fixture(scope="module")
    def genuine_selection() -> dict[str, Any]:
        assert SELECTION_PATH.is_file(), f"acceptance selection missing: {SELECTION_PATH}"
        with SELECTION_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="module")
    def genuine_tg5() -> dict[str, Any]:
        assert TG5_PATH.is_file(), f"acceptance tg5 missing: {TG5_PATH}"
        with TG5_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="module")
    def genuine_corpus() -> dict[str, Any]:
        assert CORPUS_PATH.is_file(), f"acceptance corpus missing: {CORPUS_PATH}"
        with CORPUS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="module")
    def genuine_shadow_receipt() -> dict[str, Any]:
        assert SHADOW_RECEIPT_PATH.is_file(), (
            f"acceptance shadow receipt missing: {SHADOW_RECEIPT_PATH}"
        )
        with SHADOW_RECEIPT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="module")
    def genuine_report() -> dict[str, Any]:
        assert REPORT_PATH.is_file(), f"acceptance report missing: {REPORT_PATH}"
        with REPORT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    def test_tg7_selection_manifest_conformance(genuine_selection: dict[str, Any]):
        errs = validate_selection(genuine_selection, repo_path=REPO_PATH)
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
        counts = {
            fam: sum(1 for c in cases if c["hostile_family"] == fam) for fam in HOSTILE_FAMILIES
        }
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
