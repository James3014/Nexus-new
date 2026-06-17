"""Evidence hygiene module: abort receipts, dedupe, claim boundary."""
from nexus.evidence.abort_receipt import AbortReceipt, write_abort_receipt, load_abort_receipt
from nexus.evidence.dedupe import DedupeManifest, DedupeEntry, normalize_instance_id, find_canonical
from nexus.evidence.claim_boundary import ClaimBoundary, evaluate_claim_boundary
from nexus.evidence.dedupe_aggregator import (
    AggregatedResult,
    aggregate_with_dedupe,
    aggregate_from_manifest_path,
    build_summary_header,
)

__all__ = [
    "AbortReceipt",
    "write_abort_receipt",
    "load_abort_receipt",
    "DedupeManifest",
    "DedupeEntry",
    "normalize_instance_id",
    "find_canonical",
    "ClaimBoundary",
    "evaluate_claim_boundary",
    "AggregatedResult",
    "aggregate_with_dedupe",
    "aggregate_from_manifest_path",
    "build_summary_header",
]
