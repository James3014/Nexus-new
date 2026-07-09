from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    LocalModelProvider,
    LocalModelProviderRequest,
    OllamaLocalModelProvider,
)

DEFAULT_CASCADE_MODELS: tuple[str, ...] = (
    "qwen2.5-coder:3b",
    "qwen2.5-coder:7b",
    "ornith:9b",
    "qwythos:9b",
)

_PROVIDER_MAP: dict[str, type[LocalModelProvider]] = {
    "InertLocalModelProvider": InertLocalModelProvider,
    "InjectedLocalModelProvider": InjectedLocalModelProvider,
    "OllamaLocalModelProvider": OllamaLocalModelProvider,
}


@dataclass(frozen=True)
class LocalCascadeRequest:
    task_id: str
    problem_statement: str
    cascade_models: tuple[str, ...] = DEFAULT_CASCADE_MODELS
    target_file: str = ""
    evidence_refs: tuple[str, ...] = ()
    provider_name: str = "InertLocalModelProvider"


@dataclass(frozen=True)
class LocalCascadeReceipt:
    task_id: str
    stages_run: tuple[str, ...]
    stages_failed: tuple[str, ...]
    winner_model: str
    winner_candidate_hash: str
    failed_at_final_stage: bool
    fail_closed: bool


def _get_provider(provider_name: str) -> LocalModelProvider:
    cls = _PROVIDER_MAP.get(provider_name)
    if cls is None:
        return InertLocalModelProvider()
    return cls()


def run_local_cascade(request: LocalCascadeRequest, *, provider: LocalModelProvider | None = None) -> LocalCascadeReceipt:
    if provider is None:
        provider = _get_provider(request.provider_name)
    stages_run: list[str] = []
    stages_failed: list[str] = []

    for model in request.cascade_models:
        provider_request = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=request.problem_statement,
            evidence_refs=request.evidence_refs,
            model_name=model,
        )
        response = provider.generate(provider_request)
        stages_run.append(model)

        if response.model_called and response.output_text.strip():
            raw_hash = hashlib.sha256(response.output_text.encode("utf-8")).hexdigest()
            return LocalCascadeReceipt(
                task_id=request.task_id,
                stages_run=tuple(stages_run),
                stages_failed=tuple(stages_failed),
                winner_model=model,
                winner_candidate_hash=raw_hash,
                failed_at_final_stage=False,
                fail_closed=False,
            )

        stages_failed.append(model)

    return LocalCascadeReceipt(
        task_id=request.task_id,
        stages_run=tuple(stages_run),
        stages_failed=tuple(stages_failed),
        winner_model="",
        winner_candidate_hash="",
        failed_at_final_stage=True,
        fail_closed=True,
    )
