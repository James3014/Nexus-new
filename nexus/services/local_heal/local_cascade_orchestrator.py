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
    attempt_id: str = "attempt-1"
    execution_profile: str = "LITE"
    phase: str = "patch"


@dataclass(frozen=True)
class LocalCascadeReceipt:
    task_id: str
    stages_run: tuple[str, ...]
    stages_failed: tuple[str, ...]
    winner_model: str
    winner_candidate_hash: str
    failed_at_final_stage: bool
    fail_closed: bool
    cross_stage_winner_stage: str = ""


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
            attempt_id=request.attempt_id,
            execution_profile=request.execution_profile,
            phase=request.phase,
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


def run_local_cascade_with_borda(
    request: LocalCascadeRequest,
    *,
    provider: LocalModelProvider | None = None,
    similarity_threshold: float = 0.85,
) -> tuple[LocalCascadeReceipt, Any | None]:
    if provider is None:
        provider = _get_provider(request.provider_name)
    stages_run: list[str] = []
    stages_failed: list[str] = []
    outputs: list[tuple[str, str]] = []

    for model in request.cascade_models:
        provider_request = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=request.problem_statement,
            evidence_refs=request.evidence_refs,
            model_name=model,
            attempt_id=request.attempt_id,
            execution_profile=request.execution_profile,
            phase=request.phase,
        )
        response = provider.generate(provider_request)
        stages_run.append(model)

        if response.model_called and response.output_text.strip():
            outputs.append((model, response.output_text))
        else:
            stages_failed.append(model)

    if not outputs:
        return (
            LocalCascadeReceipt(
                task_id=request.task_id,
                stages_run=tuple(stages_run),
                stages_failed=tuple(stages_failed),
                winner_model="",
                winner_candidate_hash="",
                failed_at_final_stage=True,
                fail_closed=True,
                cross_stage_winner_stage="",
            ),
            None,
        )

    from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
    candidates = [
        CanonicalPatchCandidate(
            source_format="SEARCH_REPLACE",
            raw_output=text,
            raw_output_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            normalized_patch=text,
            normalized_patch_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            normalization_steps=(),
            safety_flags=(),
            target_file=request.target_file,
            target_symbol="",
        )
        for _, text in outputs
    ]

    from nexus.services.local_heal.diversity_selector import select_with_diversity
    diversity_result = select_with_diversity(candidates, similarity_threshold=similarity_threshold)

    if diversity_result.fail_closed or diversity_result.selected_index < 0:
        winner_model, winner_text = outputs[0]
        winner_hash = hashlib.sha256(winner_text.encode("utf-8")).hexdigest()
        return (
            LocalCascadeReceipt(
                task_id=request.task_id,
                stages_run=tuple(stages_run),
                stages_failed=tuple(stages_failed),
                winner_model=winner_model,
                winner_candidate_hash=winner_hash,
                failed_at_final_stage=False,
                fail_closed=False,
                cross_stage_winner_stage=winner_model,
            ),
            diversity_result,
        )

    winner_idx = diversity_result.selected_index
    winner_model = outputs[winner_idx][0] if winner_idx < len(outputs) else ""
    winner_text = outputs[winner_idx][1] if winner_idx < len(outputs) else ""
    winner_hash = hashlib.sha256(winner_text.encode("utf-8")).hexdigest() if winner_text else ""

    return (
        LocalCascadeReceipt(
            task_id=request.task_id,
            stages_run=tuple(stages_run),
            stages_failed=tuple(stages_failed),
            winner_model=winner_model,
            winner_candidate_hash=winner_hash,
            failed_at_final_stage=False,
            fail_closed=False,
            cross_stage_winner_stage=winner_model,
        ),
        diversity_result,
    )
