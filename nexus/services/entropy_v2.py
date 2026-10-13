"""Entropy Guard v2: flag credential-like high-entropy segments in an output under review.

Calibration (2026-10-13, Nexus-new #1907, on this repository's own corpus: every
``nexus/**/*.py``, ``scripts/**/*.py``, ``tests/**/*.py`` and ``docs/**/*.md`` file vs
random alphanumeric secrets of 20-64 chars, ``sk-``/``ghp_`` style keys):

* The original rule (whole-text Shannon entropy > 4.5 bits/char) cannot discriminate:
  whole-document entropy grows with length and alphabet, so it vetoed 80% of real Python
  files and 100% of Markdown docs (CJK prose reaches 5-7.6 bits/char), while a 24-char
  random key scores ~4.25 and passes.
* Per-segment entropy separates them: runs of >= 20 credential characters
  (``[A-Za-z0-9+=!@#$%^&*()~?<>[]{}|]``, so ``_ - . / :`` and whitespace split identifiers,
  paths and prose into short segments) that mix upper case, lower case and digits.  At
  4.1 bits/char over 6,296 corpus files: 1.1% of files flagged (mostly fake-secret test
  fixtures and hash literals), 86% of random alphanumeric keys and 95% of random keys with
  symbols caught (misses are mostly 20-24 char keys).

``text_entropy`` (whole text) is still reported but no longer decides the verdict.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9+=!@#$%^&*()~?<>\[\]{}|]{20,}")
SEGMENT_ENTROPY_THRESHOLD = 4.1  # bits/char, calibrated above
TOKEN_ENTROPY_THRESHOLD = 3.5


def _mixed_classes(segment: str) -> bool:
    return (
        any(c.isdigit() for c in segment)
        and any(c.isupper() for c in segment)
        and any(c.islower() for c in segment)
    )


class EntropyGuardV2:
    """Multi-dimensional entropy audit of an output (never of the task text)."""

    def __init__(
        self,
        token_threshold: float = TOKEN_ENTROPY_THRESHOLD,
        segment_threshold: float = SEGMENT_ENTROPY_THRESHOLD,
    ):
        self.token_threshold = token_threshold
        self.segment_threshold = segment_threshold

    def audit_payload(self, text: str, tokens: List[int] | None = None) -> Dict[str, Any]:
        text_entropy = self._shannon(text)
        token_entropy = self._shannon_tokens(tokens) if tokens else 0.0
        segment_entropies = [
            self._shannon(seg) for seg in SEGMENT_PATTERN.findall(text or "") if _mixed_classes(seg)
        ]
        max_segment_entropy = max(segment_entropies, default=0.0)
        flagged = sum(1 for value in segment_entropies if value > self.segment_threshold)
        is_vetoed = flagged > 0 or token_entropy > self.token_threshold
        logger.info(
            "[Entropy-v2] text=%.2f max_segment=%.2f flagged=%d tokens=%.2f -> %s",
            text_entropy,
            max_segment_entropy,
            flagged,
            token_entropy,
            "VETO" if is_vetoed else "PASS",
        )
        return {
            "text_entropy": text_entropy,
            "token_entropy": token_entropy,
            "max_segment_entropy": max_segment_entropy,
            "high_entropy_segments": flagged,
            "segment_threshold": self.segment_threshold,
            "status": "VETOED" if is_vetoed else "PASSED",
        }

    @staticmethod
    def _shannon(text: str) -> float:
        if not text:
            return 0.0
        prob = [float(text.count(c)) / len(text) for c in dict.fromkeys(text)]
        return -sum(p * math.log2(p) for p in prob)

    @staticmethod
    def _shannon_tokens(tokens: List[int]) -> float:
        if not tokens:
            return 0.0
        prob = [float(tokens.count(t)) / len(tokens) for t in dict.fromkeys(tokens)]
        return -sum(p * math.log2(p) for p in prob)
