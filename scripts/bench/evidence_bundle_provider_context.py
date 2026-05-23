from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelLockContext:
    with_models: set[str]
    without_models: set[str]
    model_lock: dict[str, Any]


def model_names(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("model_name") or "").strip() for row in rows if str(row.get("model_name") or "").strip()}


def build_model_lock_context(
    *,
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
    environ: Mapping[str, str] | None = None,
) -> ModelLockContext:
    environ = environ if environ is not None else os.environ
    with_models = model_names(with_rows)
    without_models = model_names(without_rows)
    with_model_name = _first_model_name(with_models)
    without_model_name = _first_model_name(without_models)
    return ModelLockContext(
        with_models=with_models,
        without_models=without_models,
        model_lock={
            "without_model_name": without_model_name,
            "with_model_name": with_model_name,
            "same_model": bool(with_models and without_models and with_models == without_models),
            "env_model_name": str(environ.get("NEXUS_GEMINI_MODEL_NAME") or ""),
            "direct_model_name": str(environ.get("NEXUS_DIRECT_GEMINI_MODEL") or ""),
            "codex_model_name": str(environ.get("NEXUS_CODEX_MODEL_NAME") or ""),
            "direct_codex_model_name": str(environ.get("NEXUS_DIRECT_CODEX_MODEL") or ""),
            "prompt_transport": str(environ.get("NEXUS_GATEWAY_PROMPT_TRANSPORT") or ""),
            "compact_prompt": str(environ.get("NEXUS_GATEWAY_COMPACT_PROMPT") or "").strip().lower()
            in {"1", "true", "yes"},
        },
    )


def _first_model_name(models: set[str]) -> str:
    return sorted(models)[0] if models else ""
