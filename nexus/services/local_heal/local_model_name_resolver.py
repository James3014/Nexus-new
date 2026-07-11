"""Canonical local Ollama model name resolution.

Single boundary for alias → installed model tag mapping.
Does NOT pull models, does NOT guess families, does NOT invent tags.
Unknown names pass through unchanged so the provider can fail closed with a receipt.
"""
from __future__ import annotations

from dataclasses import dataclass


# Exact-match aliases only. Keys are policy/legacy short tags; values are
# installed Ollama tags known to this mainline. Do not add fuzzy prefixes.
_CANONICAL_LOCAL_MODEL_ALIASES: dict[str, str] = {
    "qwen2.5-coder:7b": "qwen2.5-coder:7b-instruct",
}


@dataclass(frozen=True)
class ResolvedLocalModelName:
    requested_name: str
    resolved_name: str
    resolution_source: str
    alias_applied: bool


def resolve_local_model_name(requested_name: str) -> ResolvedLocalModelName:
    """Resolve a requested local model name to a canonical Ollama tag.

    - Exact alias hit → mapped tag, alias_applied=True
    - Empty/blank → empty, no alias
    - Unknown → requested unchanged, alias_applied=False (provider may 404)
    """
    raw = str(requested_name or "").strip()
    if not raw:
        return ResolvedLocalModelName(
            requested_name=raw,
            resolved_name=raw,
            resolution_source="empty_model_name",
            alias_applied=False,
        )

    mapped = _CANONICAL_LOCAL_MODEL_ALIASES.get(raw)
    if mapped is not None and mapped != raw:
        return ResolvedLocalModelName(
            requested_name=raw,
            resolved_name=mapped,
            resolution_source="canonical_alias_map",
            alias_applied=True,
        )

    if mapped is not None and mapped == raw:
        return ResolvedLocalModelName(
            requested_name=raw,
            resolved_name=raw,
            resolution_source="already_canonical",
            alias_applied=False,
        )

    # Already the canonical target of a known alias
    if raw in _CANONICAL_LOCAL_MODEL_ALIASES.values():
        return ResolvedLocalModelName(
            requested_name=raw,
            resolved_name=raw,
            resolution_source="already_canonical",
            alias_applied=False,
        )

    return ResolvedLocalModelName(
        requested_name=raw,
        resolved_name=raw,
        resolution_source="passthrough_unknown",
        alias_applied=False,
    )
