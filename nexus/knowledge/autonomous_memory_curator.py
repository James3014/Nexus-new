from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    OllamaLocalModelProvider,
)


@dataclass(frozen=True)
class Trajectory:
    step_id: str
    action: str
    result: str
    memory_decision: str


@dataclass(frozen=True)
class HarnessUpdate:
    recommendations: list[str]
    timestamp: float


AUTOMEM_PROMPT_TEMPLATE = """You are an autonomous memory curator. Analyze the following task trajectories and identify which memory decisions were wrong and what strategies should be used instead.

Trajectories (step_id / action / result / memory_decision):
{trajectories_json}

Respond in JSON format:
{{"recommendations": ["recommendation 1", "recommendation 2", ...]}}
"""


class AutonomousMemoryCurator:
    def __init__(self, meta_llm_provider: str = "stub", every_n_steps: int = 1000) -> None:
        self._meta_llm_provider = meta_llm_provider
        self._every_n_steps = every_n_steps

    def should_curate(self, step_count: int) -> bool:
        return step_count > 0 and step_count % self._every_n_steps == 0

    def curate(self, trajectories: list[Trajectory]) -> HarnessUpdate:
        automem_llm = os.environ.get("NEXUS_AUTOMEM_LLM", "").strip()
        if not automem_llm:
            return HarnessUpdate(recommendations=[], timestamp=time.time())

        try:
            traj_data = [
                {"step_id": t.step_id, "action": t.action, "result": t.result, "memory_decision": t.memory_decision}
                for t in trajectories
            ]
            prompt = AUTOMEM_PROMPT_TEMPLATE.format(
                trajectories_json=json.dumps(traj_data, indent=2)
            )
            provider = OllamaLocalModelProvider()
            request = LocalModelProviderRequest(
                task_id="automem_curation",
                prompt=prompt,
                evidence_refs=(),
                model_name=automem_llm,
                api_type="generate",
            )
            response = provider.generate(request)
            recommendations = _parse_automem_response(response.output_text)
        except Exception:
            recommendations = []

        return HarnessUpdate(recommendations=recommendations, timestamp=time.time())


def _parse_automem_response(raw_text: str) -> list[str]:
    if not raw_text:
        return []
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start:end+1])
            recs = parsed.get("recommendations", [])
            if isinstance(recs, list):
                return [str(r).strip() for r in recs if r]
        except (json.JSONDecodeError, TypeError):
            pass
    return []
