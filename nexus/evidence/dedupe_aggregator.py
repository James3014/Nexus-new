"""
Dedupe Aggregator: Aggregate benchmark results with deduplication.

Provides raw and deduped views for benchmark summary reports.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from nexus.evidence.dedupe import (
    DedupeManifest,
    normalize_instance_id,
    find_canonical,
    load_dedupe_manifest,
)


@dataclass
class AggregatedResult:
    """Benchmark aggregation result with raw and deduped views."""
    raw_total: int = 0
    raw_solved: int = 0
    deduped_total: int = 0
    deduped_solved: int = 0
    excluded_aliases: List[str] = field(default_factory=list)
    dedupe_manifest_hash: str = ""
    raw_rate: float = 0.0
    deduped_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "raw_total": self.raw_total,
            "raw_solved": self.raw_solved,
            "raw_rate": self.raw_rate,
            "deduped_total": self.deduped_total,
            "deduped_solved": self.deduped_solved,
            "deduped_rate": self.deduped_rate,
            "excluded_aliases": self.excluded_aliases,
            "dedupe_manifest_hash": self.dedupe_manifest_hash,
        }


def aggregate_with_dedupe(
    receipts: List[Dict],
    manifest: DedupeManifest,
) -> AggregatedResult:
    """
    Aggregate receipts with deduplication.
    
    Args:
        receipts: List of receipt dicts (must have 'instance_id', 'solve_eligible')
        manifest: DedupeManifest with canonical/alias mappings
    
    Returns:
        AggregatedResult with raw and deduped views
    """
    raw_total = len(receipts)
    raw_solved = sum(1 for r in receipts if r.get("solve_eligible", False))

    seen_canonicals: Dict[str, bool] = {}
    excluded: List[str] = []

    for receipt in receipts:
        instance_id = receipt.get("instance_id", "")
        canonical = find_canonical(instance_id, manifest)
        solved = receipt.get("solve_eligible", False)

        if canonical in seen_canonicals:
            excluded.append(instance_id)
            continue

        seen_canonicals[canonical] = solved

    deduped_total = len(seen_canonicals)
    deduped_solved = sum(1 for v in seen_canonicals.values() if v)

    manifest_json = json.dumps(manifest.to_dict(), sort_keys=True)
    manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()[:16]

    result = AggregatedResult(
        raw_total=raw_total,
        raw_solved=raw_solved,
        deduped_total=deduped_total,
        deduped_solved=deduped_solved,
        excluded_aliases=excluded,
        dedupe_manifest_hash=manifest_hash,
    )
    result.raw_rate = raw_solved / raw_total if raw_total > 0 else 0.0
    result.deduped_rate = deduped_solved / deduped_total if deduped_total > 0 else 0.0

    return result


def aggregate_from_manifest_path(
    receipts: List[Dict],
    manifest_path: Path,
) -> AggregatedResult:
    """Aggregate using a manifest file path."""
    manifest = load_dedupe_manifest(manifest_path)
    return aggregate_with_dedupe(receipts, manifest)


def build_summary_header(
    result: AggregatedResult,
    report_type: str = "focused_internal_rerun",
    receipt_present_count: int = 0,
    receipt_expected_count: int = 0,
) -> dict:
    """
    P0.1c: Build a report header with claim boundary and dedupe summary.
    
    Every report should have this header to prevent simulated/internal data
    from being used as public claims.
    """
    from nexus.evidence.claim_boundary import evaluate_claim_boundary

    receipt_present_all = (receipt_present_count == receipt_expected_count) and receipt_expected_count > 0
    claim = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=result.deduped_solved > 0 and receipt_present_all,
        receipt_present=receipt_present_all,
        model_calls=0,
        visible_tests_passed=result.deduped_solved,
        hidden_tests_passed=0,
    )

    claim_dict = claim.to_dict()
    claim_dict["receipt_present_count"] = receipt_present_count
    claim_dict["receipt_expected_count"] = receipt_expected_count
    claim_dict["receipt_present_all"] = receipt_present_all
    claim_dict["receipt_coverage"] = f"{receipt_present_count}/{receipt_expected_count}" if receipt_expected_count > 0 else "0/0"

    return {
        "report_type": report_type,
        "claim_boundary": claim_dict,
        "dedupe_summary": result.to_dict(),
    }
