from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Phase6Metrics:
    mismatch_lt_0_5_last20: int
    mismatch_max_last20: float
    proof_ratio_min_last20: float
    best_precision: float


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSONL: {path}")
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
    return rows


def compute_phase6_metrics(rows: list[dict]) -> Phase6Metrics:
    if not rows:
        return Phase6Metrics(
            mismatch_lt_0_5_last20=0,
            mismatch_max_last20=999.0,
            proof_ratio_min_last20=0.0,
            best_precision=0.0,
        )

    last20 = rows[-20:]
    mismatches = [float(r.get("mismatch_rate", 999.0)) for r in last20]
    proofs = [float(r.get("proof_ratio", 0.0)) for r in last20]
    precisions: list[float] = []
    for row in rows:
        if row.get("best_precision") is not None:
            precisions.append(float(row.get("best_precision", 0.0)))
            continue
        if row.get("precision_alpha") is not None:
            precisions.append(float(row.get("precision_alpha", 0.0)))
            continue
        params = row.get("params")
        if isinstance(params, dict) and params.get("PRECISION_ALPHA") is not None:
            precisions.append(float(params.get("PRECISION_ALPHA", 0.0)))
            continue
        if isinstance(params, dict) and params.get("PRECISION") is not None:
            precisions.append(float(params.get("PRECISION", 0.0)))

    return Phase6Metrics(
        mismatch_lt_0_5_last20=len([m for m in mismatches if m < 0.5]),
        mismatch_max_last20=max(mismatches) if mismatches else 999.0,
        proof_ratio_min_last20=min(proofs) if proofs else 0.0,
        best_precision=max(precisions) if precisions else 0.0,
    )


def gate_passed(metrics: Phase6Metrics) -> bool:
    return (
        metrics.mismatch_lt_0_5_last20 >= 20
        and metrics.mismatch_max_last20 < 0.5
        and metrics.proof_ratio_min_last20 >= 95.0
    )
