"""Online A/B 20261013b finding 2: text-only providers return the edit operation as JSON text.

agy always returns plain text. Before the fix, ``_ask_unified_candidate`` wrapped any text
response as ``{"patch": text}``, so a correct ``{"operation": "replace", ...}`` answer was
written over the whole target file and the tests failed.
"""

from __future__ import annotations

import json
from pathlib import Path

from nexus.research.sprint_service import LLMCandidateGenerator, _parse_operation_payload

SOURCE = (
    "def apply_events(events):\n"
    "    state = {'count': 0, 'seen': []}\n"
    "    for event in events:\n"
    "        state['count'] += int(event.get('delta', 0))\n"
    "        state['seen'].append(event.get('id'))\n"
    "    return state\n"
)

# Verbatim provider text from receipt sprint-1a81ffaba5cc-s0-a1 (run 20261013b, _diag/).
AGY_OPERATION_TEXT = (
    "{\n"
    '  "operation": "replace",\n'
    "  \"target_snippet\": \"        state['count'] += int(event.get('delta', 0))\\n"
    "        state['seen'].append(event.get('id'))\",\n"
    '  "replacement": "        event_id = event.get(\'id\')\\n'
    "        if event_id not in state['seen']:\\n"
    "            state['count'] += int(event.get('delta', 0))\\n"
    "            state['seen'].append(event_id)\"\n"
    "}\n"
)


def _receipt(text: str) -> dict:
    return {
        "terminal_status": "SUCCEEDED",
        "online": {
            "name": "online",
            "status": "SUCCEEDED",
            "response": {
                "provider": "agy",
                "invoked": True,
                "output_delivered": True,
                "provider_call_count": 1,
                "response": text,
                "raw_response": text,
            },
        },
    }


def _generator(monkeypatch, tmp_path: Path, text: str) -> LLMCandidateGenerator:
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True)
    monkeypatch.setattr(generator, "_workspace_revision", lambda: "revision-op-json-001")
    monkeypatch.setattr(generator, "model_chain", ["gemini-3.8-flash-medium"])
    monkeypatch.setattr(
        generator.gateway, "ask_unified", lambda *_a, **_k: _receipt(text), raising=False
    )
    return generator


def _run(code: str):
    namespace: dict = {}
    exec(compile(code, "target.py", "exec"), namespace)  # noqa: S102 - test fixture code
    return namespace["apply_events"]


def test_agy_operation_json_text_is_applied_as_edit_not_whole_file(monkeypatch, tmp_path: Path):
    generator = _generator(monkeypatch, tmp_path, AGY_OPERATION_TEXT)

    code, metadata = generator.generate(
        source_code=SOURCE, task="fix duplicates", mutation_hint="", seed=0
    )

    assert not code.lstrip().startswith("{"), "operation JSON was written as the whole file"
    apply_events = _run(code)
    # visible happy path and hidden idempotence on duplicate events
    assert apply_events([{"id": "a", "delta": 2}, {"id": "b", "delta": 3}]) == {
        "count": 5,
        "seen": ["a", "b"],
    }
    assert apply_events([{"id": "a", "delta": 2}, {"id": "a", "delta": 2}]) == {
        "count": 2,
        "seen": ["a"],
    }
    assert metadata["candidate_response_path"] == "operation_json"
    assert metadata["llm_edit_protocol"] == "replace"


def test_fenced_operation_json_is_parsed():
    fenced = "```json\n" + AGY_OPERATION_TEXT.strip() + "\n```"
    parsed = _parse_operation_payload(fenced)
    assert parsed is not None
    assert parsed["operation"] == "replace"


def test_plain_source_text_keeps_whole_file_fallback(monkeypatch, tmp_path: Path):
    fixed = SOURCE.replace("    return state\n", "    return dict(state)\n")
    generator = _generator(monkeypatch, tmp_path, fixed)

    code, metadata = generator.generate(source_code=SOURCE, task="fix", mutation_hint="", seed=0)

    assert metadata["candidate_response_path"] == "whole_file_text"
    assert code == fixed


def test_json_without_edit_keys_is_not_an_operation_payload():
    assert _parse_operation_payload(json.dumps({"answer": "ok"})) is None
    assert _parse_operation_payload("{not json") is None
    assert _parse_operation_payload(json.dumps({"operation": 3})) is None


def test_model_text_cannot_inject_status_or_runtime_metadata(monkeypatch, tmp_path: Path):
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True)
    monkeypatch.setattr(generator, "_workspace_revision", lambda: "revision-op-json-002")
    text = json.dumps({
        "operation": "replace",
        "target_snippet": "a",
        "replacement": "b",
        "status": "APPROVED",
        "tokens_used": 999,
        "gateway_token_source": "model",
        "candidate_response_path": "structured",
    })
    receipt = _receipt(text)
    receipt["online"]["status"] = "FAILED"
    monkeypatch.setattr(generator.gateway, "ask_unified", lambda *_a, **_k: receipt, raising=False)

    out, _raw, _unified = generator._ask_unified_candidate(
        prompt="p", payload="x", task="t", seed=0, attempt=1, model="m"
    )

    assert out["status"] == "FAIL"
    assert "tokens_used" not in out
    assert "gateway_token_source" not in out
    assert out["candidate_response_path"] == "operation_json"
    assert out["replacement"] == "b"
