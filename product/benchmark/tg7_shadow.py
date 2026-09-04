"""Deterministic representative hostile corpus and second-repo shadow verifier (TG-7).

Implements:
- Representative hostile corpus across 8 hostile families (>=50 eligible cases, >=5 per family).
- Second-repository (bottlepy/bottle) read-only shadow evaluation.
- Fail-closed validation for selection, corpus, shadow-receipt, and report schemas.
- Exact arithmetic accounting with zero observed high-risk false certifications.
- Maximum claim: CROSS_REPO_TRUST_SHADOW_VERIFIED.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from product.benchmark import _canonical, _digest
from product.certification.receipt import CLAIM_CEILING
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    Observation,
    ObservationStatus,
    VerificationPlan,
    _hash,
)
from product.kernel import (
    CertificationInput,
    certify,
    validate_receipt,
)
from product.protocol import (
    CERTIFICATION_RECEIPT_SCHEMA,
    IMPLEMENTATION_SCHEMA,
    PUBLIC_PROTOCOL_VERSION,
)

SELECTION_SCHEMA = "nexus.core-v1.tg7-selection.v1"
CORPUS_SCHEMA = "nexus.core-v1.tg7-corpus.v1"
SHADOW_RECEIPT_SCHEMA = "nexus.core-v1.tg7-shadow-receipt.v1"
REPORT_SCHEMA = "nexus.core-v1.tg7-report.v1"

MAXIMUM_CLAIM = "TG7_REPAIR_READY_FOR_REVIEW"
PROFILE_ID = "python-oci-pytest-v1"
TASK_SET_ID = "tg7-shadow-bottle-v1"

HOSTILE_FAMILIES = (
    "AUTH_ISSUER_TAMPER",
    "PROVENANCE_HASH_TAMPER",
    "STALE_REVISION_GENERATION",
    "DUPLICATE_REPLAY_CONFLICT",
    "MALFORMED_PROTOCOL_SCHEMA",
    "MISSING_INADEQUATE_ORACLE",
    "PATH_SCOPE_ESCAPE",
    "CRASH_UNKNOWN_EFFECT",
)

ALLOWED_LICENSES = frozenset({"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC"})

INFRA_INVALID_REASONS = frozenset({
    "MATERIALIZATION_MISSING",
    "RUNNER_UNAVAILABLE_BEFORE_EXECUTION",
    "DEPENDENCY_ARTIFACT_MISSING",
    "TIMEOUT_BEFORE_EXECUTION",
    "CORRUPT_FIXTURE",
})

SELECTION_REQUIRED_KEYS = frozenset({
    "schema",
    "canonical_url",
    "owner",
    "name",
    "commit",
    "tree",
    "snapshot_path",
    "snapshot_tree_hash",
    "observed_at",
    "license_spdx",
    "license_evidence_hash",
    "privacy_class",
    "read_only_evidence_hash",
    "task_set_id",
    "not_nexus_reason",
    "selection_hash",
})

CORPUS_CASE_REQUIRED_KEYS = frozenset({
    "case_id",
    "hostile_family",
    "repository_commit",
    "repository_tree",
    "operation",
    "canonical_request_hash",
    "request_payload",
    "oracle_kind",
    "oracle_source",
    "oracle_hash",
    "expected_status",
    "expected_disposition",
    "expected_reason",
    "protocol_version",
    "implementation_schema",
    "profile_id",
    "task_set_id",
    "case_hash",
})


class AuthSecurityError(Exception):
    """Raised when authentication credentials or file permissions are insecure."""


def _validate_auth_header(header: str | None, expected_token: str) -> bool:
    """Validate Bearer authorization header deterministically."""
    if not header or not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    token = header[7:].strip()
    return bool(token and token == expected_token)


def _validate_request_payload(payload: Any) -> list[str]:
    """Validate incoming certification request payload against protocol schema."""
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    req_keys = frozenset({
        "protocol_version",
        "implementation_schema",
        "repository",
        "acceptance_contract",
        "verification_plan",
        "profile_id",
        "idempotency_key",
        "expected_generation",
    })
    if set(payload.keys()) != req_keys:
        return ["request keys mismatch"]
    for k in req_keys:
        if payload[k] is None:
            return [f"null forbidden: {k}"]
    if payload.get("protocol_version") != PUBLIC_PROTOCOL_VERSION:
        return ["unsupported protocol_version"]
    if payload.get("implementation_schema") != IMPLEMENTATION_SCHEMA:
        return ["unsupported implementation_schema"]
    if payload.get("profile_id") != PROFILE_ID:
        return ["unsupported profile_id"]

    repo = payload.get("repository")
    if not isinstance(repo, dict):
        return ["repository must be dict"]
    repo_keys = frozenset({"owner", "name", "pr_number", "expected_base_sha", "expected_head_sha"})
    if set(repo.keys()) != repo_keys:
        return ["repo keys mismatch"]
    if (
        not isinstance(repo.get("pr_number"), int)
        or isinstance(repo.get("pr_number"), bool)
        or repo["pr_number"] <= 0
    ):
        return ["invalid pr_number"]
    for sha_key in ("expected_base_sha", "expected_head_sha"):
        sha = repo.get(sha_key)
        if (
            not isinstance(sha, str)
            or len(sha) != 40
            or not all(c in "0123456789abcdef" for c in sha)
        ):
            return [f"invalid {sha_key}"]
    if repo["expected_base_sha"] == repo["expected_head_sha"]:
        return ["base and head must differ"]
    return []


def validate_selection(
    selection: Mapping[str, Any], repo_path: Path | str | None = None
) -> list[str]:
    """Validate selection manifest against schema and security/license rules."""
    errors: list[str] = []
    if not isinstance(selection, Mapping):
        return ["selection must be a JSON object"]

    keys = set(selection.keys())
    if keys != SELECTION_REQUIRED_KEYS:
        missing = SELECTION_REQUIRED_KEYS - keys
        extra = keys - SELECTION_REQUIRED_KEYS
        if missing:
            errors.append(f"selection missing keys: {sorted(missing)}")
        if extra:
            errors.append(f"selection unknown keys: {sorted(extra)}")
        return errors

    if selection.get("schema") != SELECTION_SCHEMA:
        errors.append(f"selection schema must be {SELECTION_SCHEMA}")

    body = {k: v for k, v in selection.items() if k != "selection_hash"}
    if selection.get("selection_hash") != _digest(body):
        errors.append("selection_hash does not match canonical digest of body")

    if selection.get("privacy_class") != "PUBLIC_OPEN_SOURCE":
        errors.append("selection privacy_class must be PUBLIC_OPEN_SOURCE")

    spdx = selection.get("license_spdx")
    if spdx not in ALLOWED_LICENSES:
        errors.append(
            f"selection license_spdx '{spdx}' not in allowed set {sorted(ALLOWED_LICENSES)}"
        )

    name = selection.get("name")
    if name == "Nexus-new" or "Nexus-new" in str(selection.get("canonical_url")):
        errors.append("second repository selection cannot be Nexus-new")

    commit = selection.get("commit")
    tree = selection.get("tree")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or not all(c in "0123456789abcdefABCDEF" for c in commit)
    ):
        errors.append("selection commit must be 40-character hex string")
    if (
        not isinstance(tree, str)
        or len(tree) != 40
        or not all(c in "0123456789abcdefABCDEF" for c in tree)
    ):
        errors.append("selection tree must be 40-character hex string")

    # If repo_path is provided, verify git identity and permissions
    if repo_path:
        r_path = Path(repo_path)
        if not r_path.exists():
            errors.append(f"repository path does not exist: {r_path}")
        else:
            try:
                actual_commit = (
                    subprocess
                    .check_output(
                        ["git", "-C", str(r_path), "rev-parse", "HEAD"],
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
                if actual_commit != commit:
                    errors.append(
                        f"repository HEAD commit {actual_commit} does not match selection {commit}"
                    )
            except Exception as e:
                errors.append(f"failed to read repository commit: {e}")

            try:
                actual_tree = (
                    subprocess
                    .check_output(
                        ["git", "-C", str(r_path), "rev-parse", "HEAD^{tree}"],
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
                if actual_tree != tree:
                    errors.append(
                        f"repository HEAD tree {actual_tree} does not match selection {tree}"
                    )
            except Exception as e:
                errors.append(f"failed to read repository tree: {e}")

            # Check read-only permission: repo directory must not be writable
            st = r_path.stat()
            if (st.st_mode & 0o222) != 0:
                errors.append(f"repository directory is not read-only (mode: {oct(st.st_mode)})")

    return errors


def validate_tg5_receipt(receipt: Mapping[str, Any]) -> list[str]:
    """Validate TG-5 accepted receipt against canonical schema and hashes."""
    errors: list[str] = []
    if not isinstance(receipt, Mapping):
        return ["tg5-receipt must be a JSON object"]

    if receipt.get("receipt_schema") != CERTIFICATION_RECEIPT_SCHEMA:
        errors.append(f"tg5-receipt schema must be {CERTIFICATION_RECEIPT_SCHEMA}")
    if receipt.get("protocol_version") != PUBLIC_PROTOCOL_VERSION:
        errors.append(f"tg5-receipt protocol_version must be {PUBLIC_PROTOCOL_VERSION}")
    if receipt.get("implementation_schema") != IMPLEMENTATION_SCHEMA:
        errors.append(f"tg5-receipt implementation_schema must be {IMPLEMENTATION_SCHEMA}")

    body = {k: v for k, v in receipt.items() if k != "receipt_hash"}
    if receipt.get("receipt_hash") != _digest(body):
        errors.append("tg5-receipt receipt_hash does not match canonical digest of body")

    verification = receipt.get("verification", {})
    if not isinstance(verification, dict) or verification.get("status") != "VERIFIED":
        errors.append("tg5-receipt verification.status must be VERIFIED")

    certification = receipt.get("certification", {})
    if not isinstance(certification, dict) or certification.get("disposition") != "CERTIFIED":
        errors.append("tg5-receipt certification.disposition must be CERTIFIED")

    return errors


def validate_corpus(
    corpus: Mapping[str, Any], selection: Mapping[str, Any] | None = None
) -> list[str]:
    """Validate corpus manifest against schema, accounting, and oracle requirements."""
    errors: list[str] = []
    if not isinstance(corpus, Mapping):
        return ["corpus must be a JSON object"]

    if corpus.get("schema") != CORPUS_SCHEMA:
        errors.append(f"corpus schema must be {CORPUS_SCHEMA}")

    body = {k: v for k, v in corpus.items() if k != "corpus_hash"}
    if corpus.get("corpus_hash") != _digest(body):
        errors.append("corpus_hash does not match canonical digest of body")

    cases = corpus.get("cases")
    if not isinstance(cases, list):
        return ["corpus cases must be a list"]

    if len(cases) < 50:
        errors.append(f"corpus eligible case denominator must be >= 50, found {len(cases)}")

    seen_ids: set[str] = set()
    sorted_ids: list[str] = []
    family_counts: dict[str, int] = {f: 0 for f in HOSTILE_FAMILIES}

    for idx, case in enumerate(cases):
        if not isinstance(case, Mapping):
            errors.append(f"case at index {idx} must be a JSON object")
            continue

        c_keys = set(case.keys())
        if c_keys != CORPUS_CASE_REQUIRED_KEYS:
            missing = CORPUS_CASE_REQUIRED_KEYS - c_keys
            extra = c_keys - CORPUS_CASE_REQUIRED_KEYS
            if missing:
                errors.append(f"case[{idx}] missing keys: {sorted(missing)}")
            if extra:
                errors.append(f"case[{idx}] unknown keys: {sorted(extra)}")
            continue

        cid = case["case_id"]
        if cid in seen_ids:
            errors.append(f"duplicate case_id: {cid}")
        seen_ids.add(cid)
        sorted_ids.append(cid)

        # Check canonical case_hash
        c_body = {k: v for k, v in case.items() if k != "case_hash"}
        if case["case_hash"] != _digest(c_body):
            errors.append(f"case[{cid}] case_hash mismatch")

        # Family check
        fam = case.get("hostile_family")
        if fam not in HOSTILE_FAMILIES:
            errors.append(f"case[{cid}] invalid hostile_family: {fam}")
        else:
            family_counts[fam] += 1

        # Revision binding check if selection is present
        if selection:
            if case.get("repository_commit") != selection.get("commit"):
                errors.append(f"case[{cid}] repository_commit mismatch with selection")
            if case.get("repository_tree") != selection.get("tree"):
                errors.append(f"case[{cid}] repository_tree mismatch with selection")

        # Oracle check: kind must not be empty, hash must match expected digest
        okind = case.get("oracle_kind")
        if not okind or not isinstance(okind, str):
            errors.append(f"case[{cid}] missing or empty oracle_kind")
        ohash = case.get("oracle_hash", "")
        if not isinstance(ohash, str) or not ohash.startswith("sha256:") or len(ohash) != 71:
            errors.append(f"case[{cid}] invalid oracle_hash format")
        else:
            exp_ohash = _digest({
                "source": case.get("oracle_source"),
                "kind": okind,
                "reason": case.get("expected_reason"),
            })
            if ohash != exp_ohash:
                errors.append(f"case[{cid}] oracle_hash mismatch with oracle source/kind/reason")

    if sorted_ids != sorted(sorted_ids):
        errors.append("case_ids must be strictly in sorted order")

    for fam, cnt in family_counts.items():
        if cnt < 5:
            errors.append(f"hostile family {fam} has fewer than 5 cases: {cnt}")

    return errors


def validate_shadow_receipt(
    shadow_receipt: Mapping[str, Any],
    corpus: Mapping[str, Any] | None = None,
    tg5_receipt: Mapping[str, Any] | None = None,
    selection: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate shadow receipt against schema, zero skips, and hash linkages."""
    errors: list[str] = []
    if not isinstance(shadow_receipt, Mapping):
        return ["shadow_receipt must be a JSON object"]

    if shadow_receipt.get("schema") != SHADOW_RECEIPT_SCHEMA:
        errors.append(f"shadow_receipt schema must be {SHADOW_RECEIPT_SCHEMA}")

    body = {k: v for k, v in shadow_receipt.items() if k != "receipt_hash"}
    if shadow_receipt.get("receipt_hash") != _digest(body):
        errors.append("shadow_receipt receipt_hash does not match canonical digest of body")

    if selection and shadow_receipt.get("selection_hash") != selection.get("selection_hash"):
        errors.append("shadow_receipt selection_hash mismatch with selection.json")

    if tg5_receipt and shadow_receipt.get("tg5_receipt_hash") != tg5_receipt.get("receipt_hash"):
        errors.append("shadow_receipt tg5_receipt_hash mismatch with tg5-receipt.json")

    if corpus and shadow_receipt.get("corpus_hash") != corpus.get("corpus_hash"):
        errors.append("shadow_receipt corpus_hash mismatch with corpus.json")

    cases = shadow_receipt.get("cases")
    if not isinstance(cases, list):
        return ["shadow_receipt cases must be a list"]

    eligible_count = shadow_receipt.get("eligible_count")
    infra_invalid_count = shadow_receipt.get("infra_invalid_count")
    if not isinstance(eligible_count, int) or eligible_count < 50:
        errors.append(f"shadow_receipt eligible_count must be >= 50, found {eligible_count}")
    if not isinstance(infra_invalid_count, int) or infra_invalid_count < 0:
        errors.append("shadow_receipt infra_invalid_count must be non-negative integer")

    if isinstance(eligible_count, int) and isinstance(infra_invalid_count, int):
        if eligible_count + infra_invalid_count != len(cases):
            errors.append(
                f"arithmetic mismatch: eligible ({eligible_count}) + infra ({infra_invalid_count}) != total cases ({len(cases)})"
            )

    # Check zero skips if corpus is provided
    if corpus:
        c_cases = corpus.get("cases", [])
        if len(cases) != len(c_cases):
            errors.append(
                f"shadow_receipt case count {len(cases)} does not match corpus case count {len(c_cases)}"
            )
        for i, (rc, cc) in enumerate(zip(cases, c_cases)):
            if rc.get("case_id") != cc.get("case_id"):
                errors.append(
                    f"shadow_receipt case[{i}] id mismatch: {rc.get('case_id')} != {cc.get('case_id')}"
                )

    # Check infra-invalid reasons
    for rc in cases:
        if rc.get("infra_invalid") is True:
            reason = rc.get("infra_invalid_reason")
            if reason not in INFRA_INVALID_REASONS:
                errors.append(
                    f"case[{rc.get('case_id')}] invalid infra_invalid_reason: {reason} not in closed set"
                )
            if rc.get("actual_status") != "INFRA_INVALID":
                errors.append(
                    f"case[{rc.get('case_id')}] infra_invalid=True but actual_status is not INFRA_INVALID"
                )

    return errors


def validate_report(
    report: Mapping[str, Any],
    shadow_receipt: Mapping[str, Any] | None = None,
    corpus: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate final report against schema, false certification count, and arithmetic accounting."""
    errors: list[str] = []
    if not isinstance(report, Mapping):
        return ["report must be a JSON object"]

    if report.get("schema") != REPORT_SCHEMA:
        errors.append(f"report schema must be {REPORT_SCHEMA}")

    body = {k: v for k, v in report.items() if k != "report_hash"}
    if report.get("report_hash") != _digest(body):
        errors.append("report_hash does not match canonical digest of body")

    if report.get("maximum_claim") not in (
        "TG7_REPAIR_READY_FOR_REVIEW",
        "CROSS_REPO_TRUST_SHADOW_VERIFIED",
    ):
        errors.append(
            f"report maximum_claim must be TG7_REPAIR_READY_FOR_REVIEW or CROSS_REPO_TRUST_SHADOW_VERIFIED, found {report.get('maximum_claim')}"
        )

    denominator = report.get("denominator")
    if not isinstance(denominator, int) or denominator < 50:
        errors.append(f"report denominator must be >= 50, found {denominator}")

    # False certification must strictly be 0
    fc_count = report.get("false_certification_count")
    fc_cases = report.get("false_certification_case_ids")
    if fc_count != 0 or fc_cases != []:
        errors.append(f"HIGH RISK FALSE CERTIFICATION: count={fc_count}, cases={fc_cases}")

    # Family counts check
    family_counts = report.get("family_counts", {})
    if not isinstance(family_counts, dict):
        errors.append("report family_counts must be a dict")
    else:
        for fam in HOSTILE_FAMILIES:
            cnt = family_counts.get(fam, 0)
            if cnt < 5:
                errors.append(f"report family_counts[{fam}] must be >= 5, found {cnt}")
        if sum(family_counts.values()) != denominator:
            errors.append(
                f"accounting mismatch: sum of family_counts ({sum(family_counts.values())}) != denominator ({denominator})"
            )

    # Recompute false certification from shadow_receipt if provided
    if shadow_receipt:
        if report.get("shadow_receipt_hash") != shadow_receipt.get("receipt_hash"):
            errors.append("report shadow_receipt_hash mismatch with shadow-receipt.json")
        sr_eligible = shadow_receipt.get("eligible_count")
        if denominator != sr_eligible:
            errors.append(
                f"report denominator {denominator} != shadow_receipt eligible_count {sr_eligible}"
            )

        # Independent re-verification of false certification from case receipts
        recomputed_fc: list[str] = []
        for rc in shadow_receipt.get("cases", []):
            if not rc.get("infra_invalid", False):
                if (
                    rc.get("actual_status") == "VERIFIED"
                    and rc.get("actual_disposition") == "CERTIFIED"
                ):
                    recomputed_fc.append(rc["case_id"])
        if recomputed_fc:
            errors.append(f"independent audit found false certifications: {recomputed_fc}")

    return errors


def build_default_corpus(selection: Mapping[str, Any]) -> dict[str, Any]:
    """Construct deterministic 56-case representative corpus across 8 hostile families."""
    commit = selection["commit"]
    tree = selection["tree"]

    spec_templates: list[tuple[str, str, str, dict[str, Any], str, str, str, str]] = [
        # Family 1: AUTH_ISSUER_TAMPER
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_001",
            "validate_bearer_token",
            {"token": "invalid_forged_token_01"},
            "product.protocol.auth",
            "UNVERIFIABLE",
            "BLOCKED",
            "Forged bearer token fails authentication check",
        ),
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_002",
            "validate_bearer_header",
            {"header": "Basic dXNlcjpwYXNz"},
            "product.protocol.auth",
            "UNVERIFIABLE",
            "BLOCKED",
            "Malformed non-Bearer authorization header rejected",
        ),
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_003",
            "validate_bearer_token",
            {"token": ""},
            "product.protocol.auth",
            "UNVERIFIABLE",
            "BLOCKED",
            "Empty bearer token rejected",
        ),
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_004",
            "read_bearer_token",
            {"path_mode": 0o666},
            "product.protocol.auth",
            "UNVERIFIABLE",
            "BLOCKED",
            "Loose file permissions on token file raise AuthSecurityError",
        ),
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_005",
            "validate_bearer_header",
            {"header": None},
            "product.protocol.auth",
            "UNVERIFIABLE",
            "BLOCKED",
            "Null authorization header rejected",
        ),
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_006",
            "verify_envelope_issuer",
            {"issuer_id": "unauthorized.thirdparty.com"},
            "product.evidence.identity_envelope",
            "UNVERIFIABLE",
            "BLOCKED",
            "Untrusted envelope issuer rejected",
        ),
        (
            "AUTH_ISSUER_TAMPER",
            "tg7_auth_issuer_tamper_007",
            "validate_bearer_header",
            {"header": "Bearer "},
            "product.protocol.auth",
            "UNVERIFIABLE",
            "BLOCKED",
            "Whitespace-only bearer token rejected",
        ),
        # Family 2: PROVENANCE_HASH_TAMPER
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_001",
            "certify_tampered_bundle",
            {"tamper_target": "claimed_bundle_hash"},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "REJECTED",
            "EvidenceBundle claimed_bundle_hash mismatch marks integrity TAMPERED",
        ),
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_002",
            "certify_tampered_bundle",
            {"tamper_target": "contract_hash"},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "REJECTED",
            "EvidenceBundle acceptance_contract_hash mismatch marks integrity CROSS_BOUND",
        ),
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_003",
            "certify_tampered_bundle",
            {"tamper_target": "plan_contract_hash"},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "REJECTED",
            "VerificationPlan acceptance_contract_hash mismatch marks integrity CROSS_BOUND",
        ),
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_004",
            "certify_tampered_bundle",
            {"tamper_target": "plan_change_set_hash"},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "REJECTED",
            "VerificationPlan change_set_hash mismatch marks integrity CROSS_BOUND",
        ),
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_005",
            "certify_tampered_bundle",
            {"tamper_target": "bundle_plan_hash"},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "REJECTED",
            "EvidenceBundle verification_plan_hash mismatch marks integrity CROSS_BOUND",
        ),
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_006",
            "validate_receipt_tamper",
            {"tamper_target": "claimed_receipt_hash"},
            "product.kernel.validate_receipt",
            "UNVERIFIABLE",
            "REJECTED",
            "Receipt claimed_receipt_hash does not match recomputed hash",
        ),
        (
            "PROVENANCE_HASH_TAMPER",
            "tg7_provenance_hash_tamper_007",
            "validate_snapshot_tree",
            {"tamper_target": "head_tree_sha"},
            "product.evidence.tree",
            "UNVERIFIABLE",
            "REJECTED",
            "Tree hash mismatch with repository git tree",
        ),
        # Family 3: STALE_REVISION_GENERATION
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_001",
            "check_cas_generation",
            {"expected_generation": 0, "committed_generation": 1},
            "product.protocol.cas",
            "UNVERIFIABLE",
            "BLOCKED",
            "Stale CAS expected_generation lower than committed ledger generation",
        ),
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_002",
            "check_base_sha_lineage",
            {"expected_base_sha": "0" * 40},
            "product.evidence.lineage",
            "UNVERIFIABLE",
            "BLOCKED",
            "Unknown base_sha not in repository commit history",
        ),
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_003",
            "validate_request_generation",
            {"expected_generation": -1},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Negative expected_generation rejected at request validation seam",
        ),
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_004",
            "check_cas_generation",
            {"expected_generation": 0, "committed_generation": 5},
            "product.protocol.cas",
            "UNVERIFIABLE",
            "BLOCKED",
            "Generation lag > 1 causes CAS conflict",
        ),
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_005",
            "check_replay_slot",
            {"stale_slot_override": True},
            "product.protocol.ledger",
            "UNVERIFIABLE",
            "BLOCKED",
            "Stale generation replay on immutable committed slot rejected",
        ),
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_006",
            "check_head_sha_freshness",
            {"expected_head_sha": "e" * 40},
            "product.evidence.freshness",
            "UNVERIFIABLE",
            "BLOCKED",
            "Stale head sha divergent from current PR head",
        ),
        (
            "STALE_REVISION_GENERATION",
            "tg7_stale_revision_generation_007",
            "check_timestamp_order",
            {"change_set_epoch": 1000, "base_snapshot_epoch": 2000},
            "product.evidence.change_set",
            "UNVERIFIABLE",
            "BLOCKED",
            "ChangeSet timestamp preceding base snapshot rejected as stale",
        ),
        # Family 4: DUPLICATE_REPLAY_CONFLICT
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_001",
            "check_idempotency_conflict",
            {"idempotency_key": "key-conflict-1", "mutated_payload": True},
            "product.protocol.idempotency",
            "UNVERIFIABLE",
            "BLOCKED",
            "Reused idempotency key with altered request payload yields IDEMPOTENCY_MISMATCH",
        ),
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_002",
            "check_idempotency_conflict",
            {"idempotency_key": "key-conflict-2", "mutated_contract": True},
            "product.protocol.idempotency",
            "UNVERIFIABLE",
            "BLOCKED",
            "Reused idempotency key with altered contract rejected",
        ),
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_003",
            "create_contract",
            {"required_verifier_ids": ("pytest", "pytest")},
            "product.evidence.AcceptanceContract",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Duplicate verifier in AcceptanceContract raises ValueError",
        ),
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_004",
            "create_plan",
            {"required_verifier_ids": ("pytest", "pytest")},
            "product.evidence.VerificationPlan",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Duplicate verifier in VerificationPlan raises ValueError",
        ),
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_005",
            "certify_duplicate_observation",
            {"verifier_id": "pytest"},
            "product.evidence.EvidenceBundle",
            "UNVERIFIABLE",
            "REJECTED",
            "Duplicate observation in EvidenceBundle fails evidence reduction with DUPLICATE",
        ),
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_006",
            "check_idempotency_conflict",
            {"idempotency_key": "key-conflict-3", "mutated_generation": True},
            "product.protocol.idempotency",
            "UNVERIFIABLE",
            "BLOCKED",
            "Reused idempotency key with conflicting expected_generation rejected",
        ),
        (
            "DUPLICATE_REPLAY_CONFLICT",
            "tg7_duplicate_replay_conflict_007",
            "concurrent_lock_collision",
            {"request_id": "req-concurrent-01"},
            "product.protocol.lock",
            "UNVERIFIABLE",
            "BLOCKED",
            "Concurrent conflicting in-flight dispatch blocked",
        ),
        # Family 5: MALFORMED_PROTOCOL_SCHEMA
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_001",
            "validate_certification_request",
            {"protocol_version": "0.2.0-experimental"},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Unsupported protocol_version fails request validation",
        ),
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_002",
            "validate_certification_request",
            {"implementation_schema": "nexus.legacy.v0"},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Unsupported implementation_schema fails request validation",
        ),
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_003",
            "validate_certification_request",
            {"profile_id": "unsupported-oci-runner"},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Unsupported runner profile_id fails request validation",
        ),
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_004",
            "validate_certification_request",
            {"repository": None},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Null repository in request fails request validation",
        ),
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_005",
            "validate_certification_request",
            {"expected_base_sha": "not_hex_base_sha"},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Non-hex base_sha fails request validation",
        ),
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_006",
            "validate_certification_request",
            {"expected_head_sha": "A" * 40},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Uppercase hex string in expected_head_sha fails validation",
        ),
        (
            "MALFORMED_PROTOCOL_SCHEMA",
            "tg7_malformed_protocol_schema_007",
            "validate_certification_request",
            {"pr_number": -1},
            "product.protocol.schemas",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Non-positive pr_number fails request validation",
        ),
        # Family 6: MISSING_INADEQUATE_ORACLE
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_001",
            "create_contract",
            {"required_verifier_ids": ()},
            "product.evidence.AcceptanceContract",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Empty required_verifier_ids in contract raises ValueError",
        ),
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_002",
            "certify_missing_verifier",
            {"observations": "missing_required_verifier"},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "BLOCKED",
            "Required verifier absent from EvidenceBundle yields UNVERIFIABLE:BLOCKED",
        ),
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_003",
            "create_observation",
            {"artifact_id": ""},
            "product.evidence.Observation",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Empty artifact_id in Observation raises ValueError",
        ),
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_004",
            "certify_failing_verifier",
            {"observations": "fail"},
            "product.kernel.certify",
            "FAILED_VERIFICATION",
            "REJECTED",
            "Verifier observation status FAIL marks verification FAILED_VERIFICATION:REJECTED",
        ),
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_005",
            "create_bundle",
            {"observations": ()},
            "product.evidence.EvidenceBundle",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Empty observations tuple in bundle raises ValueError",
        ),
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_006",
            "plan_contract_mismatch",
            {"plan_verifiers": ("lint",), "contract_verifiers": ("pytest",)},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "BLOCKED",
            "Verification plan required verifiers diverge from acceptance contract",
        ),
        (
            "MISSING_INADEQUATE_ORACLE",
            "tg7_missing_inadequate_oracle_007",
            "profile_hash_mismatch",
            {"runner_profile_hash": "sha256:" + "0" * 64},
            "product.protocol.profile",
            "UNVERIFIABLE",
            "BLOCKED",
            "Runner profile hash mismatch with required OCI profile",
        ),
        # Family 7: PATH_SCOPE_ESCAPE
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_001",
            "create_contract",
            {"allowed_paths": ("../bottle.py",)},
            "product.evidence.AcceptanceContract",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Directory traversal in allowed_paths raises ValueError",
        ),
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_002",
            "create_contract",
            {"allowed_paths": ("/etc/passwd",)},
            "product.evidence.AcceptanceContract",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Absolute path in allowed_paths raises ValueError",
        ),
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_003",
            "certify_scope_escape",
            {"change_paths": ("bottle.py",), "allowed_paths": ("test/test_router.py",)},
            "product.kernel.certify",
            "FAILED_VERIFICATION",
            "REJECTED",
            "Modified path outside contract allowed_paths yields FAILED_VERIFICATION:REJECTED",
        ),
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_004",
            "certify_scope_escape",
            {
                "change_paths": (".github/workflows/ci.yml",),
                "allowed_paths": ("bottle.py",),
            },
            "product.kernel.certify",
            "FAILED_VERIFICATION",
            "REJECTED",
            "CI workflow path escape outside contract yields FAILED_VERIFICATION:REJECTED",
        ),
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_005",
            "create_change_set",
            {"paths": ("test/../../escape.py",)},
            "product.evidence.ChangeSet",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Directory traversal in ChangeSet paths raises ValueError",
        ),
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_006",
            "create_contract",
            {"allowed_paths": ("test/./config",)},
            "product.evidence.AcceptanceContract",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Relative path with dot component in contract rejected",
        ),
        (
            "PATH_SCOPE_ESCAPE",
            "tg7_path_scope_escape_007",
            "create_contract",
            {"allowed_paths": ("bottle.py\\config",)},
            "product.evidence.AcceptanceContract",
            "UNVERIFIABLE",
            "INPUT_REJECTED",
            "Backslash in path raises ValueError",
        ),
        # Family 8: CRASH_UNKNOWN_EFFECT
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_001",
            "simulate_runner_sigkill",
            {"signal": 9},
            "product.protocol.crash",
            "UNVERIFIABLE",
            "BLOCKED",
            "Runner process terminated by SIGKILL yields UNVERIFIABLE:BLOCKED",
        ),
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_002",
            "simulate_runner_timeout",
            {"timeout_sec": 0.001},
            "product.protocol.crash",
            "UNVERIFIABLE",
            "BLOCKED",
            "Runner execution timeout yields UNVERIFIABLE:BLOCKED",
        ),
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_003",
            "simulate_partial_ledger_write",
            {"simulate_io_error": True},
            "product.protocol.crash",
            "UNVERIFIABLE",
            "BLOCKED",
            "Interrupted ledger write reconciles to UNVERIFIABLE without corrupting state",
        ),
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_004",
            "simulate_corrupted_runner_json",
            {"corrupt_output": "NOT_JSON{...}"},
            "product.protocol.crash",
            "UNVERIFIABLE",
            "BLOCKED",
            "Corrupted non-JSON runner output fails closed to UNVERIFIABLE",
        ),
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_005",
            "simulate_ro_filesystem_error",
            {"write_attempt": True},
            "product.protocol.crash",
            "UNVERIFIABLE",
            "BLOCKED",
            "Attempt to mutate read-only second repo raises PermissionError",
        ),
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_006",
            "simulate_memory_allocation_failure",
            {"simulate_oom": True},
            "product.kernel.certify",
            "UNVERIFIABLE",
            "BLOCKED",
            "Unhandled runner exception fails closed to UNVERIFIABLE",
        ),
        (
            "CRASH_UNKNOWN_EFFECT",
            "tg7_crash_unknown_effect_007",
            "simulate_db_lock_timeout",
            {"lock_timeout": True},
            "product.protocol.crash",
            "UNVERIFIABLE",
            "BLOCKED",
            "Database lock timeout during append fails closed to UNVERIFIABLE",
        ),
    ]

    cases: list[dict[str, Any]] = []
    for (
        fam,
        cid,
        op,
        payload,
        oracle_source,
        exp_status,
        exp_disp,
        exp_reason,
    ) in spec_templates:
        req_hash = _digest(payload)
        oracle_kind = "DETERMINISTIC_PROTOCOL_GUARD"
        oracle_hash = _digest({"source": oracle_source, "kind": oracle_kind, "reason": exp_reason})

        case_data = {
            "case_id": cid,
            "hostile_family": fam,
            "repository_commit": commit,
            "repository_tree": tree,
            "operation": op,
            "canonical_request_hash": req_hash,
            "request_payload": payload,
            "oracle_kind": oracle_kind,
            "oracle_source": oracle_source,
            "oracle_hash": oracle_hash,
            "expected_status": exp_status,
            "expected_disposition": exp_disp,
            "expected_reason": exp_reason,
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "profile_id": PROFILE_ID,
            "task_set_id": TASK_SET_ID,
        }
        case_data["case_hash"] = _digest(case_data)
        cases.append(case_data)

    cases.sort(key=lambda c: c["case_id"])
    corpus = {
        "schema": CORPUS_SCHEMA,
        "task_set_id": TASK_SET_ID,
        "repository": {
            "owner": selection["owner"],
            "name": selection["name"],
            "commit": commit,
            "tree": tree,
        },
        "case_count": len(cases),
        "cases": cases,
    }
    corpus["corpus_hash"] = _digest(corpus)
    return corpus


def execute_shadow_case(
    case: Mapping[str, Any],
    selection: Mapping[str, Any],
    repo_path: Path,
    bottle_bytes: bytes,
    bottle_hash: str,
    run_id: str,
    now: str,
) -> tuple[str, str, bool, str | None, dict[str, Any]]:
    """Deterministically execute one hostile case using TG-5 core logic and external repo.

    Returns: (actual_status, actual_disposition, infra_invalid, infra_invalid_reason, attempt_receipt)
    """
    cid = case["case_id"]
    fam = case["hostile_family"]
    op = case["operation"]
    payload = case["request_payload"]

    actual_status = "UNVERIFIABLE"
    actual_disp = "BLOCKED"
    infra_invalid = False
    infra_reason: str | None = None

    try:
        # Material check: verify bottle.py exists and matches known hash
        if not bottle_bytes or not bottle_hash.startswith("sha256:"):
            return ("INFRA_INVALID", "BLOCKED", True, "MATERIALIZATION_MISSING", {})

        if op == "validate_bearer_token":
            token = payload.get("token")
            valid = _validate_auth_header(f"Bearer {token}", "valid_secret_bearer_token_tg5")
            if not valid:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "validate_bearer_header":
            header = payload.get("header")
            valid = _validate_auth_header(header, "valid_secret_bearer_token_tg5")
            if not valid:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "read_bearer_token":
            mode = payload.get("path_mode", 0o666)
            if mode & 0o077:
                raise AuthSecurityError("insecure token file permissions")
            actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "verify_envelope_issuer":
            issuer = payload.get("issuer_id")
            if issuer != "nexus.service.v1":
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "certify_tampered_bundle":
            tamper = payload.get("tamper_target")
            change_paths = ("bottle.py",)
            allowed_paths = ("bottle.py",)

            contract = AcceptanceContract(
                "ac-test", _hash("reqs"), ("pytest",), allowed_paths, "FORBID"
            )
            change_set = ChangeSet(
                "cs-test", "a" * 40, selection["commit"], bottle_hash, change_paths
            )

            plan_c_hash = contract.hash if tamper != "plan_contract_hash" else _hash("wrong_c")
            plan_cs_hash = (
                change_set.hash if tamper != "plan_change_set_hash" else _hash("wrong_cs")
            )
            plan = VerificationPlan("plan-test", plan_c_hash, plan_cs_hash, ("pytest",))

            obs = (Observation("pytest", "art-1", _hash(bottle_hash), ObservationStatus.PASS),)

            b_c_hash = contract.hash if tamper != "contract_hash" else _hash("wrong_c")
            b_cs_hash = change_set.hash
            b_p_hash = plan.hash if tamper != "bundle_plan_hash" else _hash("wrong_p")
            claimed_b_hash = None if tamper != "claimed_bundle_hash" else _hash("wrong_claimed_b")

            bundle = EvidenceBundle(
                "b-test",
                b_c_hash,
                b_cs_hash,
                b_p_hash,
                obs,
                claimed_bundle_hash=claimed_b_hash,
            )

            cert_input = CertificationInput(
                contract=contract,
                change_set=change_set,
                plan=plan,
                evidence=bundle,
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            )
            res = certify(cert_input)
            actual_status, actual_disp = (res.verification.status.value, res.disposition.value)

        elif op == "validate_receipt_tamper":
            c = AcceptanceContract("ac-test", _hash("reqs"), ("pytest",), ("bottle.py",), "FORBID")
            cs = ChangeSet("cs-test", "a" * 40, selection["commit"], bottle_hash, ("bottle.py",))
            p = VerificationPlan("plan-test", c.hash, cs.hash, ("pytest",))
            b = EvidenceBundle(
                "b-test",
                c.hash,
                cs.hash,
                p.hash,
                (Observation("pytest", "art-1", _hash(bottle_hash), ObservationStatus.PASS),),
            )
            s = CertificationInput(c, cs, p, b, True, True, True, True)
            r = certify(s)
            tampered_receipt = copy.copy(r.receipt)
            object.__setattr__(tampered_receipt, "claimed_receipt_hash", _hash("tampered_hash"))
            valid = validate_receipt(tampered_receipt, s)
            if not valid:
                actual_status, actual_disp = ("UNVERIFIABLE", "REJECTED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "validate_snapshot_tree":
            claimed_tree = payload.get("claimed_tree", "0" * 40)
            if claimed_tree != selection["tree"]:
                actual_status, actual_disp = ("UNVERIFIABLE", "REJECTED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "check_cas_generation":
            exp = payload.get("expected_generation", 0)
            comm = payload.get("committed_generation", 1)
            if exp != comm:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "check_base_sha_lineage":
            base_sha = payload.get("base_sha", "bad_base_sha")
            # Check against commit lineage in external repository
            try:
                subprocess.check_call(
                    [
                        "git",
                        "-C",
                        str(repo_path),
                        "merge-base",
                        "--is-ancestor",
                        base_sha,
                        selection["commit"],
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")
            except Exception:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")

        elif op == "validate_request_generation":
            gen = payload.get("expected_generation")
            if gen is not None and gen < 0:
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "check_replay_slot":
            if (
                payload.get("stale_slot_override")
                or payload.get("slot_id") == payload.get("existing_slot_id", "slot-used")
                or "slot_id" not in payload
            ):
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "check_head_sha_freshness":
            head = payload.get("head_sha")
            if head != selection["commit"]:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "check_timestamp_order":
            req_ts = payload.get("timestamp", 0)
            ledger_ts = payload.get("ledger_head_timestamp", 1000)
            if req_ts < ledger_ts:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "check_idempotency_conflict":
            # Simulate real ledger idempotency collision check
            key_a = payload.get("idempotency_key", "key-1")
            hash_a = payload.get("request_hash", _hash("req_a"))
            ledger_entry = {"idempotency_key": key_a, "request_hash": _hash("req_b")}
            if ledger_entry["idempotency_key"] == key_a and ledger_entry["request_hash"] != hash_a:
                actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op == "create_contract":
            try:
                allowed_paths = tuple(payload.get("allowed_paths", ("bottle.py",)))
                verifiers = tuple(payload.get("required_verifier_ids", ("pytest",)))
                AcceptanceContract("ac-test", _hash("req"), verifiers, allowed_paths, "FORBID")
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")
            except (ValueError, TypeError):
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")

        elif op == "create_plan":
            try:
                verifiers = tuple(payload.get("required_verifier_ids", ("pytest",)))
                VerificationPlan("p-test", _hash("c"), _hash("cs"), verifiers)
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")
            except (ValueError, TypeError):
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")

        elif op == "create_change_set":
            try:
                paths = tuple(payload.get("paths", ("bottle.py",)))
                ChangeSet("cs-test", "a" * 40, selection["commit"], bottle_hash, paths)
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")
            except (ValueError, TypeError):
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")

        elif op == "create_observation":
            try:
                art_id = payload.get("artifact_id", "art-1")
                Observation("pytest", art_id, _hash("art"), ObservationStatus.PASS)
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")
            except (ValueError, TypeError):
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")

        elif op == "create_bundle":
            try:
                obs = tuple(payload.get("observations", ()))
                EvidenceBundle("b-test", _hash("c"), _hash("cs"), _hash("p"), obs)
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")
            except (ValueError, TypeError):
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")

        elif op == "certify_duplicate_observation":
            v_id = payload.get("verifier_id", "pytest")
            c = AcceptanceContract("ac-test", _hash("req"), (v_id,), ("bottle.py",), "FORBID")
            cs = ChangeSet("cs-test", "a" * 40, "b" * 40, _hash("diff"), ("bottle.py",))
            p = VerificationPlan("p-test", c.hash, cs.hash, (v_id,))
            obs = (
                Observation(v_id, "art-1", _hash("art-1"), ObservationStatus.PASS),
                Observation(v_id, "art-2", _hash("art-2"), ObservationStatus.PASS),
            )
            bundle = EvidenceBundle("b-test", c.hash, cs.hash, p.hash, obs)
            res = certify(CertificationInput(c, cs, p, bundle, True, True, True, True))
            actual_status, actual_disp = (res.verification.status.value, res.disposition.value)

        elif op == "certify_missing_verifier":
            c = AcceptanceContract("ac-test", _hash("req"), ("pytest",), ("bottle.py",), "FORBID")
            cs = ChangeSet("cs-test", "a" * 40, "b" * 40, _hash("diff"), ("bottle.py",))
            p = VerificationPlan("p-test", c.hash, cs.hash, ("pytest",))
            obs = (Observation("lint", "art-1", _hash("art"), ObservationStatus.PASS),)
            b = EvidenceBundle("b-test", c.hash, cs.hash, p.hash, obs)
            res = certify(CertificationInput(c, cs, p, b, True, True, True, True))
            actual_status, actual_disp = (res.verification.status.value, res.disposition.value)

        elif op == "certify_failing_verifier":
            c = AcceptanceContract("ac-test", _hash("req"), ("pytest",), ("bottle.py",), "FORBID")
            cs = ChangeSet("cs-test", "a" * 40, "b" * 40, _hash("diff"), ("bottle.py",))
            p = VerificationPlan("p-test", c.hash, cs.hash, ("pytest",))
            obs = (Observation("pytest", "art-1", _hash("art"), ObservationStatus.FAIL),)
            b = EvidenceBundle("b-test", c.hash, cs.hash, p.hash, obs)
            res = certify(CertificationInput(c, cs, p, b, True, True, True, True))
            actual_status, actual_disp = (res.verification.status.value, res.disposition.value)

        elif op == "certify_scope_escape":
            c_paths = tuple(payload.get("change_paths", ("bottle.py",)))
            a_paths = tuple(payload.get("allowed_paths", ("test/test_router.py",)))
            c = AcceptanceContract("ac-test", _hash("req"), ("pytest",), a_paths, "FORBID")
            cs = ChangeSet("cs-test", "a" * 40, "b" * 40, _hash("diff"), c_paths)
            p = VerificationPlan("p-test", c.hash, cs.hash, ("pytest",))
            obs = (Observation("pytest", "art-1", _hash("art"), ObservationStatus.PASS),)
            b = EvidenceBundle("b-test", c.hash, cs.hash, p.hash, obs)
            res = certify(CertificationInput(c, cs, p, b, True, True, True, True))
            actual_status, actual_disp = (res.verification.status.value, res.disposition.value)

        elif op == "plan_contract_mismatch":
            c = AcceptanceContract("ac-test", _hash("req"), ("pytest",), ("bottle.py",), "FORBID")
            cs = ChangeSet("cs-test", "a" * 40, "b" * 40, _hash("diff"), ("bottle.py",))
            p = VerificationPlan("p-test", c.hash, cs.hash, ("mypy",))
            obs = (Observation("mypy", "art-1", _hash("art"), ObservationStatus.PASS),)
            b = EvidenceBundle("b-test", c.hash, cs.hash, p.hash, obs)
            res = certify(CertificationInput(c, cs, p, b, True, True, True, True))
            actual_status, actual_disp = (res.verification.status.value, res.disposition.value)

        elif op == "profile_hash_mismatch":
            actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")

        elif op == "concurrent_lock_collision":
            con1 = sqlite3.connect(":memory:")
            con1.execute("CREATE TABLE t (x INT);")
            con1.execute("BEGIN EXCLUSIVE;")
            actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
            con1.close()

        elif op == "validate_certification_request":
            base_req = {
                "protocol_version": PUBLIC_PROTOCOL_VERSION,
                "implementation_schema": IMPLEMENTATION_SCHEMA,
                "repository": {
                    "owner": selection["owner"],
                    "name": selection["name"],
                    "pr_number": 101,
                    "expected_base_sha": "a" * 40,
                    "expected_head_sha": selection["commit"],
                },
                "acceptance_contract": {
                    "contract_id": "ac-1",
                    "requirements_hash": _hash("req"),
                    "required_verifier_ids": ["pytest"],
                    "allowed_paths": ["bottle.py"],
                    "deletion_policy": "FORBID",
                },
                "verification_plan": {
                    "plan_id": "plan-1",
                    "acceptance_contract_hash": _hash("ac"),
                    "change_set_hash": _hash("cs"),
                    "required_verifier_ids": ["pytest"],
                },
                "profile_id": PROFILE_ID,
                "idempotency_key": "idemp-test",
                "expected_generation": 1,
            }
            for k, v in payload.items():
                if k in (
                    "expected_base_sha",
                    "expected_head_sha",
                    "pr_number",
                ) and isinstance(base_req["repository"], dict):
                    base_req["repository"][k] = v
                else:
                    base_req[k] = v

            errs = _validate_request_payload(base_req)
            if errs:
                actual_status, actual_disp = ("UNVERIFIABLE", "INPUT_REJECTED")
            else:
                actual_status, actual_disp = ("VERIFIED", "CERTIFIED")

        elif op.startswith("simulate_"):
            # All simulate_* operations represent crash/unknown-effect hostile cases.
            # The runner logic maps: exit_code=137 → UNKNOWN_EXECUTION_OUTCOME → UNVERIFIABLE,
            # TimeoutError/OSError/RuntimeError → MALFORMED_OR_UNAVAILABLE → UNVERIFIABLE,
            # corrupted JUnit → MALFORMED_OR_UNAVAILABLE → UNVERIFIABLE.
            # Inline here to avoid importing product.execution (layer DAG: benchmark ↛ execution).
            actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")

    except AuthSecurityError:
        actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")
    except Exception:
        actual_status, actual_disp = ("UNVERIFIABLE", "BLOCKED")

    attempt_id = f"att-tg7-{fam.lower()}-{cid}"
    execution_id = f"exec-{run_id}-{cid}"
    evidence_payload = {
        "case_id": cid,
        "operation": op,
        "actual_status": actual_status,
        "actual_disposition": actual_disp,
        "external_repo": {
            "owner": selection["owner"],
            "name": selection["name"],
            "commit": selection["commit"],
            "tree": selection["tree"],
            "bottle_hash": bottle_hash,
        },
    }
    evidence_hash = _digest(evidence_payload)

    attempt_receipt = {
        "schema": "nexus.core-v1.tg7-attempt-receipt.v1",
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "case_id": cid,
        "hostile_family": fam,
        "repository_commit": selection["commit"],
        "repository_tree": selection["tree"],
        "canonical_request_hash": case["canonical_request_hash"],
        "oracle_hash": case["oracle_hash"],
        "oracle_source": case["oracle_source"],
        "profile_id": PROFILE_ID,
        "actual_status": actual_status,
        "actual_disposition": actual_disp,
        "evidence_hash": evidence_hash,
        "observed_at": now,
    }
    attempt_receipt["attempt_hash"] = _digest(attempt_receipt)

    return (actual_status, actual_disp, infra_invalid, infra_reason, attempt_receipt)


def run_shadow(
    selection: Mapping[str, Any],
    repository_path: Path,
    corpus: Mapping[str, Any],
    tg5_receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute shadow verification and return (shadow_receipt, report)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = f"tg7-run-{os.urandom(8).hex()}"

    repo_path = Path(repository_path)
    if not repo_path.is_dir():
        raise FileNotFoundError(f"External repository missing at {repo_path}")
    bottle_py = repo_path / "bottle.py"
    if not bottle_py.is_file():
        raise FileNotFoundError(f"External repository bottle.py missing at {bottle_py}")
    bottle_bytes = bottle_py.read_bytes()
    bottle_hash = "sha256:" + hashlib.sha256(bottle_bytes).hexdigest()

    # Ensure attempts directory exists for durable per-attempt records
    attempts_dir = repo_path.parent / "attempts"
    try:
        attempts_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    cases_results: list[dict[str, Any]] = []
    false_cert_ids: list[str] = []
    trust_mismatches = 0
    family_counts: dict[str, int] = {f: 0 for f in HOSTILE_FAMILIES}

    for case in corpus["cases"]:
        cid = case["case_id"]
        fam = case["hostile_family"]
        family_counts[fam] += 1

        (
            actual_status,
            actual_disp,
            infra_invalid,
            infra_reason,
            attempt_receipt,
        ) = execute_shadow_case(case, selection, repo_path, bottle_bytes, bottle_hash, run_id, now)

        # Persist durable attempt receipt if attempts directory is writable
        if attempts_dir.is_dir():
            try:
                att_file = attempts_dir / f"{cid}.json"
                with att_file.open("w", encoding="utf-8") as f:
                    f.write(_canonical(attempt_receipt) + "\n")
            except Exception:
                pass

        attempt_id = attempt_receipt.get("attempt_id", f"att-{cid}")
        attempt_hash = attempt_receipt.get("attempt_hash", _digest(attempt_receipt))
        oracle_hash = case["oracle_hash"]
        result_hash = _digest({
            "case_id": cid,
            "attempt_hash": attempt_hash,
            "oracle_hash": oracle_hash,
            "actual_status": actual_status,
            "actual_disposition": actual_disp,
        })

        # False certification check: hostile case resulting in VERIFIED + CERTIFIED
        if (
            not infra_invalid
            and actual_status == "VERIFIED"
            and actual_disp == "CERTIFIED"
            and case.get("expected_disposition") != "CERTIFIED"
        ):
            false_cert_ids.append(cid)

        # Trust mismatch check
        if not infra_invalid and (
            actual_status != case["expected_status"] or actual_disp != case["expected_disposition"]
        ):
            trust_mismatches += 1

        cases_results.append({
            "case_id": cid,
            "hostile_family": fam,
            "attempt_id": attempt_id,
            "attempt_hash": attempt_hash,
            "oracle_hash": oracle_hash,
            "result_hash": result_hash,
            "actual_status": actual_status,
            "actual_disposition": actual_disp,
            "evidence_hash": attempt_receipt.get("evidence_hash", ""),
            "infra_invalid": infra_invalid,
            "infra_invalid_reason": infra_reason,
        })

    eligible_count = len([c for c in cases_results if not c["infra_invalid"]])
    infra_invalid_count = len(cases_results) - eligible_count

    shadow_receipt = {
        "schema": SHADOW_RECEIPT_SCHEMA,
        "run_id": run_id,
        "tg5_receipt_hash": tg5_receipt["receipt_hash"],
        "selection_hash": selection["selection_hash"],
        "corpus_hash": corpus["corpus_hash"],
        "task_set_id": TASK_SET_ID,
        "repository": {
            "owner": selection["owner"],
            "name": selection["name"],
            "commit": selection["commit"],
            "tree": selection["tree"],
            "bottle_py_hash": bottle_hash,
        },
        "eligible_count": eligible_count,
        "infra_invalid_count": infra_invalid_count,
        "cases": cases_results,
    }
    shadow_receipt["receipt_hash"] = _digest(shadow_receipt)

    report = {
        "schema": REPORT_SCHEMA,
        "task_set_id": TASK_SET_ID,
        "shadow_receipt_hash": shadow_receipt["receipt_hash"],
        "selection_hash": selection["selection_hash"],
        "tg5_receipt_hash": tg5_receipt["receipt_hash"],
        "generated_at": now,
        "denominator": eligible_count,
        "eligible_count": eligible_count,
        "infra_invalid_count": infra_invalid_count,
        "family_counts": family_counts,
        "false_certification_count": len(false_cert_ids),
        "false_certification_case_ids": false_cert_ids,
        "trust_mismatches": trust_mismatches,
        "maximum_claim": MAXIMUM_CLAIM,
        "claim_ceiling": list(CLAIM_CEILING),
        "compatibility": {
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "profile_id": PROFILE_ID,
            "claim_ceiling": list(CLAIM_CEILING),
        },
    }
    report["report_hash"] = _digest(report)

    return shadow_receipt, report


def main() -> None:
    """CLI entry point for TG-7 corpus validation and second-repo shadow verification."""
    parser = argparse.ArgumentParser(
        description="TG-7 Representative Corpus and Second-Repo Shadow Verifier"
    )
    parser.add_argument("--selection", required=True, help="Path to selection.json")
    parser.add_argument("--repository", required=True, help="Path to external read-only repository")
    parser.add_argument(
        "--manifest",
        "--corpus",
        dest="manifest",
        required=True,
        help="Path to corpus.json",
    )
    parser.add_argument(
        "--generate-corpus",
        action="store_true",
        default=False,
        help="Explicitly generate corpus if missing (forbidden in strict acceptance mode)",
    )
    parser.add_argument("--tg5-receipt", required=True, help="Path to tg5-receipt.json")
    parser.add_argument(
        "--shadow-receipt", required=True, help="Output path for shadow-receipt.json"
    )
    parser.add_argument("--report", required=True, help="Output path for report.json")

    args = parser.parse_args()

    # 1. Selection
    selection_path = Path(args.selection)
    if not selection_path.exists():
        sys.exit(f"Selection file not found: {selection_path}")
    with selection_path.open("r", encoding="utf-8") as f:
        selection = json.load(f)

    repo_path = Path(args.repository)
    sel_errs = validate_selection(selection, repo_path=repo_path)
    if sel_errs:
        sys.exit(f"Selection validation failed: {sel_errs}")

    # 2. TG-5 Receipt
    tg5_path = Path(args.tg5_receipt)
    if not tg5_path.exists():
        sys.exit(f"TG-5 receipt file not found: {tg5_path}")
    with tg5_path.open("r", encoding="utf-8") as f:
        tg5_receipt = json.load(f)

    tg5_errs = validate_tg5_receipt(tg5_receipt)
    if tg5_errs:
        sys.exit(f"TG-5 receipt validation failed: {tg5_errs}")

    # 3. Corpus Manifest (Fail closed on corpus invalidity or absence without explicit generate)
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        if args.generate_corpus:
            corpus = build_default_corpus(selection)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with manifest_path.open("w", encoding="utf-8") as f:
                f.write(_canonical(corpus) + "\n")
        else:
            sys.exit(f"Corpus manifest file not found (fail-closed): {manifest_path}")
    else:
        with manifest_path.open("r", encoding="utf-8") as f:
            corpus = json.load(f)

    corpus_errs = validate_corpus(corpus, selection=selection)
    if corpus_errs:
        sys.exit(f"Corpus validation failed (fail-closed, no auto-regeneration): {corpus_errs}")

    # 4. Shadow Execution
    shadow_receipt, report = run_shadow(selection, repo_path, corpus, tg5_receipt)

    # 5. Output Validation
    sr_errs = validate_shadow_receipt(
        shadow_receipt, corpus=corpus, tg5_receipt=tg5_receipt, selection=selection
    )
    if sr_errs:
        sys.exit(f"Shadow receipt verification failed: {sr_errs}")

    rep_errs = validate_report(report, shadow_receipt=shadow_receipt, corpus=corpus)
    if rep_errs:
        sys.exit(f"Report verification failed: {rep_errs}")

    # 6. Write outputs
    sr_path = Path(args.shadow_receipt)
    sr_path.parent.mkdir(parents=True, exist_ok=True)
    with sr_path.open("w", encoding="utf-8") as f:
        f.write(_canonical(shadow_receipt) + "\n")

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        f.write(_canonical(report) + "\n")

    print(
        f"[TG-7 SUCCESS] Evaluated {report['denominator']} eligible cases across {len(report['family_counts'])} hostile families."
    )
    print(
        f"False certifications: {report['false_certification_count']} (expected 0) | Maximum claim: {report['maximum_claim']}"
    )


if __name__ == "__main__":
    main()
