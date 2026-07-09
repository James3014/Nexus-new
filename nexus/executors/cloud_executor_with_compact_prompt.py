from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudCandidateResponse:
    raw_output: str
    raw_output_hash: str
    model_name: str
    invoked: bool
    error: str
    latency_ms: int


def run_with_compact_prompt(
    prompt: str, anchor: dict, max_tokens: int = 4000
) -> CloudCandidateResponse:
    if len(prompt) > 500:
        raise ValueError(
            f"Compact prompt budget exceeded: {len(prompt)} chars > 500 max"
        )

    if not anchor.get("target_file"):
        logger.warning("anchor.target_file is empty — no target file specified")

    return CloudCandidateResponse(
        raw_output="",
        raw_output_hash="",
        model_name="stub",
        invoked=False,
        error="stub mode not real cloud",
        latency_ms=0,
    )
