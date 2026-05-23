from __future__ import annotations

from scripts.bench.evidence_bundle_provider_context import build_model_lock_context, model_names


def test_model_names_returns_nonempty_normalized_model_set():
    assert model_names(
        [
            {"model_name": " gemini-3-flash-preview "},
            {"model_name": ""},
            {"model_name": None},
            {"model_name": "gpt-5.5"},
        ]
    ) == {"gemini-3-flash-preview", "gpt-5.5"}


def test_build_model_lock_context_centralizes_same_model_and_env_fields():
    context = build_model_lock_context(
        with_rows=[{"model_name": "gpt-5.5"}],
        without_rows=[{"model_name": "gpt-5.5"}],
        environ={
            "NEXUS_GEMINI_MODEL_NAME": "gemini-env",
            "NEXUS_DIRECT_GEMINI_MODEL": "gemini-direct",
            "NEXUS_CODEX_MODEL_NAME": "gpt-env",
            "NEXUS_DIRECT_CODEX_MODEL": "gpt-direct",
            "NEXUS_GATEWAY_PROMPT_TRANSPORT": "json",
            "NEXUS_GATEWAY_COMPACT_PROMPT": "true",
        },
    )

    assert context.with_models == {"gpt-5.5"}
    assert context.without_models == {"gpt-5.5"}
    assert context.model_lock == {
        "without_model_name": "gpt-5.5",
        "with_model_name": "gpt-5.5",
        "same_model": True,
        "env_model_name": "gemini-env",
        "direct_model_name": "gemini-direct",
        "codex_model_name": "gpt-env",
        "direct_codex_model_name": "gpt-direct",
        "prompt_transport": "json",
        "compact_prompt": True,
    }


def test_build_model_lock_context_sorts_multiple_models_for_stable_payloads():
    context = build_model_lock_context(
        with_rows=[{"model_name": "z-model"}, {"model_name": "a-model"}],
        without_rows=[{"model_name": "a-model"}],
        environ={},
    )

    assert context.model_lock["with_model_name"] == "a-model"
    assert context.model_lock["without_model_name"] == "a-model"
    assert context.model_lock["same_model"] is False
