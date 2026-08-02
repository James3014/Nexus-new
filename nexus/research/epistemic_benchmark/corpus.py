"""
Benchmark Corpus v0 — 18 synthetic cases loaded from canonical JSON data.

This module provides the public corpus (no oracle fields) and the private
oracle (separate, never written to public run directories).
Data is loaded from data/corpus_v0.json and data/oracle_v0.json.
"""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _compute_hash(obj: Any) -> str:
    return _sha256_str(_canonical_json(obj))


REQUIRED_CASE_IDS = [
    "EBR-001", "EBR-002", "EBR-003", "EBR-004", "EBR-005", "EBR-006",
    "EBR-007", "EBR-008", "EBR-009", "EBR-010", "EBR-011", "EBR-012",
    "EBR-013", "EBR-014", "EBR-015", "EBR-016", "EBR-017", "EBR-018",
]

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_CORPUS_PATH = os.path.join(_DATA_DIR, "corpus_v0.json")
_ORACLE_PATH = os.path.join(_DATA_DIR, "oracle_v0.json")

_CASES: Optional[List[Dict[str, Any]]] = None
_ORACLES: Optional[List[Dict[str, Any]]] = None
_CASES_BY_ID: Optional[Dict[str, Dict[str, Any]]] = None
_ORACLES_BY_ID: Optional[Dict[str, Dict[str, Any]]] = None


def _load_and_validate_canonical_data() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not os.path.exists(_CORPUS_PATH):
        raise FileNotFoundError(f"Canonical corpus data missing: {_CORPUS_PATH}")
    if not os.path.exists(_ORACLE_PATH):
        raise FileNotFoundError(f"Canonical oracle data missing: {_ORACLE_PATH}")

    with open(_CORPUS_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    with open(_ORACLE_PATH, "r", encoding="utf-8") as f:
        oracles = json.load(f)

    if not isinstance(cases, list) or len(cases) != len(REQUIRED_CASE_IDS):
        raise ValueError(f"Corpus must be list of {len(REQUIRED_CASE_IDS)} cases")
    if not isinstance(oracles, list) or len(oracles) != len(REQUIRED_CASE_IDS):
        raise ValueError(f"Oracle must be list of {len(REQUIRED_CASE_IDS)} items")

    case_ids: Set[str] = set()
    for case in cases:
        cid = case.get("case_id")
        if not cid or cid in case_ids:
            raise ValueError(f"Duplicate or missing case_id: {cid}")
        if case.get("schema") != "nexus.epistemic_benchmark_case.v0":
            raise ValueError(f"Invalid case schema for {cid}")
        case_ids.add(cid)

        expected_hash = case.get("public_case_sha256")
        body = {k: v for k, v in case.items() if k != "public_case_sha256"}
        computed = _compute_hash(body)
        if expected_hash != computed:
            raise ValueError(f"Case {cid} public_case_sha256 mismatch")

        mat_refs = {m.get("ref") for m in case.get("materials", []) if isinstance(m, dict)}
        for ref in case.get("available_evidence_refs", []):
            if ref not in mat_refs:
                raise ValueError(f"Case {cid} evidence ref {ref} not in materials")

    oracle_ids: Set[str] = set()
    for oracle in oracles:
        cid = oracle.get("case_id")
        if not cid or cid in oracle_ids:
            raise ValueError(f"Duplicate or missing oracle case_id: {cid}")
        if oracle.get("schema") != "nexus.epistemic_benchmark_oracle.v0":
            raise ValueError(f"Invalid oracle schema for {cid}")
        oracle_ids.add(cid)
        if cid not in case_ids:
            raise ValueError(f"Oracle case_id {cid} not in corpus")

        expected_hash = oracle.get("oracle_sha256")
        body = {k: v for k, v in oracle.items() if k != "oracle_sha256"}
        computed = _compute_hash(body)
        if expected_hash != computed:
            raise ValueError(f"Oracle {cid} oracle_sha256 mismatch")

    return cases, oracles


def _ensure_loaded() -> None:
    global _CASES, _ORACLES, _CASES_BY_ID, _ORACLES_BY_ID
    if _CASES is None:
        cases, oracles = _load_and_validate_canonical_data()
        _CASES = cases
        _ORACLES = oracles
        _CASES_BY_ID = {c["case_id"]: c for c in _CASES}
        _ORACLES_BY_ID = {o["case_id"]: o for o in _ORACLES}


def get_public_corpus() -> List[Dict[str, Any]]:
    """Return all 18 public cases (no oracle fields)."""
    _ensure_loaded()
    return [dict(c) for c in _CASES]


get_corpus = get_public_corpus


def get_public_case(case_id: str) -> Optional[Dict[str, Any]]:
    _ensure_loaded()
    c = _CASES_BY_ID.get(case_id)
    return dict(c) if c else None


def get_oracle(case_id: str) -> Optional[Dict[str, Any]]:
    """Return oracle for case_id. MUST NOT be included in public packets."""
    _ensure_loaded()
    o = _ORACLES_BY_ID.get(case_id)
    return dict(o) if o else None


def get_all_oracles() -> List[Dict[str, Any]]:
    """Return all oracles. MUST NOT be included in public run directories."""
    _ensure_loaded()
    return [dict(o) for o in _ORACLES]


def get_corpus_version() -> str:
    return "v0"
