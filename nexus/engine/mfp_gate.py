from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MFPVerdict:
    passed: bool
    reason: str
    confidence: float
    semantic_entropy: float
    history_success_rate: float


def _threshold(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def evaluate_mfp(
    *,
    confidence: float,
    semantic_entropy: float,
    history_success_rate: float,
) -> MFPVerdict:
    conf_min = _threshold("NEXUS_MFP_CONFIDENCE_MIN", 0.98)
    entropy_max = _threshold("NEXUS_MFP_ENTROPY_MAX", 0.15)
    success_min = _threshold("NEXUS_MFP_HISTORY_SUCCESS_MIN", 0.95)

    if confidence < conf_min:
        return MFPVerdict(False, "mfp_confidence_below_threshold", confidence, semantic_entropy, history_success_rate)
    if semantic_entropy > entropy_max:
        return MFPVerdict(False, "mfp_entropy_above_threshold", confidence, semantic_entropy, history_success_rate)
    if history_success_rate < success_min:
        return MFPVerdict(False, "mfp_history_success_below_threshold", confidence, semantic_entropy, history_success_rate)
    return MFPVerdict(True, "mfp_pass", confidence, semantic_entropy, history_success_rate)

