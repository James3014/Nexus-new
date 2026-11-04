#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_promotion import derive_zero_trust_v2_signed_counts  # noqa: E402
from nexus.learning.zero_trust_v2_signing_secret import (  # noqa: E402
    SECRET_ENV,
    SECRET_FILE_ENV,
    SigningSecretError,
    resolve_signing_secret,
)


DEFAULT_EVIDENCE = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PHYSICAL_SKILL_EVIDENCE_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_EVIDENCE_ACCUMULATION_2026-05-21.json")


def build_zero_trust_v2_evidence_accumulation(
    *, physical_evidence: dict, min_v2_evidence_count: int = 3, signing_secret: str | None = None
) -> dict:
    rows = [row for row in physical_evidence.get("rows", []) or [] if isinstance(row, dict)]
    rows = [row for row in rows if row.get("arm_type") in {"candidate_skill_v2", "shadow_candidate_v2", "wrong_or_quarantined_skill_v2"}]
    if physical_evidence.get("nonproduction_secret") is True:
        rows = [{**row, "nonproduction_secret": True} for row in rows]
    # Counts come only from verified, de-duplicated signed receipts, shared with the promotion
    # evaluator (#3355); the rows' own count columns are not trusted.
    by_candidate = derive_zero_trust_v2_signed_counts(rows, signing_secret=signing_secret)
    candidates = []
    for (capability_id, skill_id), item in sorted(by_candidate.items()):
        ready = (
            item["v2_evidence_count"] >= min_v2_evidence_count
            and item["v2_trust_mismatch_count"] == 0
            and item["negative_control_blocked_count"] >= 1
        )
        candidates.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "status": "READY_FOR_MANUAL_APPLY" if ready else "BLOCKED",
                "v2_evidence_count": item["v2_evidence_count"],
                "v2_trust_mismatch_count": item["v2_trust_mismatch_count"],
                "negative_control_blocked_count": item["negative_control_blocked_count"],
                "row_refs": item["row_refs"],
                "signature_rejected_row_count": item["rejected_rows"],
                "rejected_row_refs": item["rejected_row_refs"],
                "duplicate_proof_count": item["duplicate_proof_count"],
                "duplicate_identity_count": item["duplicate_identity_count"],
                "duplicate_identity_row_refs": item["duplicate_identity_row_refs"],
                "unsigned_count_mismatch_row_refs": item["unsigned_count_mismatch_row_refs"],
            }
        )
    status_counts = Counter(candidate["status"] for candidate in candidates)
    return {
        "schema": "nexus.zero_trust_v2.evidence_accumulation.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_physical_evidence": str(DEFAULT_EVIDENCE),
        "summary": {
            "candidate_count": len(candidates),
            "ready_for_manual_apply_count": status_counts.get("READY_FOR_MANUAL_APPLY", 0),
            "blocked_count": status_counts.get("BLOCKED", 0),
            "min_v2_evidence_count": min_v2_evidence_count,
            "materialization_only": bool(physical_evidence.get("summary", {}).get("materialization_only")),
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 evidence accumulation report.")
    parser.add_argument("--physical-evidence", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-v2-evidence-count", type=int, default=3)
    parser.add_argument("--secret-file", default=None, help="0600 file with the runner signing secret, to re-verify attestations")
    args = parser.parse_args(argv)
    signing_secret = None
    if args.secret_file or os.environ.get(SECRET_FILE_ENV) or os.environ.get(SECRET_ENV):
        try:
            signing_secret = resolve_signing_secret(secret_file=args.secret_file, nonproduction_default="").value
        except SigningSecretError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    result = build_zero_trust_v2_evidence_accumulation(
        physical_evidence=read_json(args.physical_evidence),
        min_v2_evidence_count=args.min_v2_evidence_count,
        signing_secret=signing_secret,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
