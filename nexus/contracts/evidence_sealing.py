from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


EVIDENCE_SEAL_SCHEMA = "nexus.evidence_seal.v1"


def seal_evidence(payload: Mapping[str, Any], *, evidence_id: str) -> dict[str, Any]:
    digest = _stable_hash(payload)
    return {
        "schema": EVIDENCE_SEAL_SCHEMA,
        "status": "PASS",
        "evidence_id": evidence_id,
        "sha256": digest,
        "evidence_seal_status": "PASS",
        "evidence_hash_status": "PASS",
        "sealed_payload": dict(payload),
        "blockers": [],
    }


def verify_evidence_seal(seal: Mapping[str, Any]) -> dict[str, Any]:
    payload = seal.get("sealed_payload")
    expected = str(seal.get("sha256") or "")
    actual = _stable_hash(payload if isinstance(payload, Mapping) else {})
    blockers: list[str] = []
    if seal.get("schema") != EVIDENCE_SEAL_SCHEMA:
        blockers.append("invalid_evidence_seal_schema")
    if not expected:
        blockers.append("missing_evidence_sha256")
    if expected and actual != expected:
        blockers.append("evidence_hash_mismatch")
    return {
        "schema": "nexus.evidence_seal_verification.v1",
        "status": "PASS" if not blockers else "RETURN",
        "evidence_id": str(seal.get("evidence_id") or ""),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "evidence_seal_status": "PASS" if not blockers else "RETURN",
        "evidence_hash_status": "PASS" if not blockers else "RETURN",
        "blockers": sorted(set(blockers)),
    }


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
