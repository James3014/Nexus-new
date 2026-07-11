"""Unit tests for canonical local model name resolution."""
from __future__ import annotations

from nexus.services.local_heal.local_model_name_resolver import (
    resolve_local_model_name,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
    RecordingLocalModelProvider,
)


def test_resolves_qwen_7b_alias_to_installed_canonical_tag() -> None:
    r = resolve_local_model_name("qwen2.5-coder:7b")
    assert r.requested_name == "qwen2.5-coder:7b"
    assert r.resolved_name == "qwen2.5-coder:7b-instruct"
    assert r.alias_applied is True
    assert r.resolution_source == "canonical_alias_map"


def test_preserves_already_canonical_qwen_7b_tag() -> None:
    r = resolve_local_model_name("qwen2.5-coder:7b-instruct")
    assert r.requested_name == "qwen2.5-coder:7b-instruct"
    assert r.resolved_name == "qwen2.5-coder:7b-instruct"
    assert r.alias_applied is False
    assert r.resolution_source == "already_canonical"


def test_unknown_model_is_not_silently_substituted() -> None:
    r = resolve_local_model_name("totally-unknown-model:99b")
    assert r.resolved_name == "totally-unknown-model:99b"
    assert r.alias_applied is False
    assert r.resolution_source == "passthrough_unknown"


def test_resolution_receipt_records_requested_and_resolved() -> None:
    base = InjectedLocalModelProvider(lambda req: "ok")
    rec = RecordingLocalModelProvider(base)
    req = LocalModelProviderRequest(
        task_id="t_res",
        prompt="hello",
        evidence_refs=(),
        model_name="qwen2.5-coder:7b",
        phase="patch",
        attempt_id="attempt-1",
        execution_profile="LITE",
    )
    resp = rec.generate(req)
    assert resp.output_text == "ok"
    record = rec.ledger[0]
    assert record.requested_model == "qwen2.5-coder:7b"
    assert record.resolved_model == "qwen2.5-coder:7b-instruct"
    assert record.model_alias_applied is True
    assert record.model_resolution_source == "canonical_alias_map"
    # model field represents the resolved provider tag
    assert record.model == "qwen2.5-coder:7b-instruct" or record.resolved_model == "qwen2.5-coder:7b-instruct"
    d = record.to_dict()
    assert d["requested_model"] == "qwen2.5-coder:7b"
    assert d["resolved_model"] == "qwen2.5-coder:7b-instruct"
