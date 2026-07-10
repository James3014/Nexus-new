from __future__ import annotations

import hashlib
import logging
import os
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


class RealCloudExecutor:
    def __init__(self) -> None:
        self.api_key = os.environ.get("NEXUS_CLOUD_API_KEY")
        if self.api_key is None:
            logger.warning("NEXUS_CLOUD_API_KEY not set — running in stub mode")

    def run_with_compact_prompt(
        self, prompt: str, anchor: dict, max_tokens: int = 4000
    ) -> CloudCandidateResponse:
        if len(prompt) > 500:
            raise ValueError(
                f"Compact prompt budget exceeded: {len(prompt)} chars > 500 max"
            )

        if self.api_key is None:
            return CloudCandidateResponse(
                raw_output="",
                raw_output_hash="",
                model_name="stub",
                invoked=False,
                error="no_api_key",
                latency_ms=0,
            )

        mock_response = f"mock_cloud_output_for_{prompt[:64]}"
        response_hash = hashlib.sha256(mock_response.encode()).hexdigest()
        return CloudCandidateResponse(
            raw_output=mock_response,
            raw_output_hash=response_hash,
            model_name="real_cloud_mock",
            invoked=True,
            error="",
            latency_ms=42,
        )
