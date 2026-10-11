from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.local_heal import lesson_embedding
from nexus.services.local_heal.learning_closure_bridge import (
    LearningClosureBridge,
    _reflect_canonical_episode,
    write_learning_closure,
)

LESSONS_RELATIVE = Path(".nexus/memory/learning_lessons.jsonl")


def _bridge(tmp_path: Path) -> LearningClosureBridge:
    return LearningClosureBridge(
        path=tmp_path / "learning_closure.jsonl",
        enable_findings=False,
        project_root=tmp_path,
    )


def _qualified_op(**overrides) -> SimpleNamespace:
    values = {
        "task_id": "task-reflect-1",
        "instance_id": "task-reflect-1",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "idempotency_key": "idem-reflect-1",
        "terminal_outcome": "SUCCEEDED",
        "receipt_path": "receipt:abc123",
        "terminal_evidence_present": True,
        "solve_eligible": True,
        "failure_reason": "",
        "final_patch": "print('ok')",
        "problem_statement": "fix the parser",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _lesson_rows(tmp_path: Path) -> list[dict]:
    path = tmp_path / LESSONS_RELATIVE
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@pytest.fixture(autouse=True)
def _writeback_on(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK", raising=False)
    monkeypatch.delenv("NEXUS_LEARNING_REFLECT_JUDGE", raising=False)
    monkeypatch.delenv("NEXUS_LEARNING_REFLECT_MODEL", raising=False)


def test_succeeded_closure_reflects_one_lesson_into_ledger(tmp_path: Path) -> None:
    closure = write_learning_closure(_qualified_op(), bridge=_bridge(tmp_path))

    reflection = closure["reflection"]
    assert reflection["reflection_status"] == "written"
    assert len(reflection["lesson_ids"]) == 1

    rows = _lesson_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["lesson_id"] == reflection["lesson_ids"][0]
    assert rows[0]["source_episode_ids"] == [closure["lesson"]["episode_id"]]


def test_repeated_closure_keeps_one_lesson_line(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    op = _qualified_op()

    first = write_learning_closure(op, bridge=bridge)
    second = write_learning_closure(op, bridge=bridge)

    assert first["reflection"]["lesson_ids"] == second["reflection"]["lesson_ids"]
    assert len(_lesson_rows(tmp_path)) == 1


def test_unqualified_closure_yields_simulated_non_retrievable_lesson(tmp_path: Path) -> None:
    op = SimpleNamespace(
        task_id="task-unq-1",
        instance_id="task-unq-1",
        idempotency_key="idem-unq-1",
        terminal_outcome="SUCCEEDED",
    )

    closure = write_learning_closure(op, bridge=_bridge(tmp_path))

    assert closure["reflection"]["reflection_status"] == "written"
    assert closure["reflection"]["evidence_origin"] == "simulated"
    rows = _lesson_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["evidence_origin"] == "simulated"
    assert rows[0]["retrieval_eligible"] is False


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info) -> None:
        return None


def test_ollama_judge_failure_falls_back_to_deterministic(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.setenv("NEXUS_LEARNING_REFLECT_JUDGE", "ollama")

    def _raise(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(lesson_embedding, "_open", _raise)

    closure = write_learning_closure(_qualified_op(), bridge=_bridge(tmp_path))

    assert closure["reflection"]["reflection_status"] == "written"
    assert closure["reflection"]["reflector_kind"] == "deterministic"
    assert len(_lesson_rows(tmp_path)) == 1


def test_ollama_judge_output_is_used_when_valid(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.setenv("NEXUS_LEARNING_REFLECT_JUDGE", "ollama")
    judge_output = (
        "```json\n"
        + json.dumps({
            "title": "Verify parser fix before closing",
            "lesson": "Run the parser regression check before marking the fix done.",
            "applies_when": ["parser"],
            "avoid_when": [],
            "confidence": 0.8,
        })
        + "\n```"
    )
    monkeypatch.setattr(
        lesson_embedding,
        "_open",
        lambda *args, **kwargs: _FakeResponse({"response": judge_output}),
    )

    closure = write_learning_closure(_qualified_op(), bridge=_bridge(tmp_path))

    assert closure["reflection"]["reflection_status"] == "written"
    assert closure["reflection"]["reflector_kind"] == "judge"
    rows = _lesson_rows(tmp_path)
    assert rows[0]["title"] == "Verify parser fix before closing"
    assert rows[0]["reflector"]["kind"] == "judge"


def test_writeback_disabled_skips_reflection_and_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK", "off")

    closure = write_learning_closure(_qualified_op(), bridge=_bridge(tmp_path))
    reflection = _reflect_canonical_episode(
        tmp_path, {"episode_id": "ep-disabled", "terminal_outcome": "SUCCEEDED"}
    )

    assert closure["writeback_status"] == "disabled"
    assert "reflection" not in closure
    assert reflection == {"reflection_status": "disabled", "lesson_ids": []}
    assert not (tmp_path / LESSONS_RELATIVE).exists()


def test_ollama_judge_request_is_json_mode_with_instruction_and_problem_summary(
    tmp_path: Path, monkeypatch
) -> None:

    monkeypatch.setenv("NEXUS_LEARNING_REFLECT_JUDGE", "ollama")
    sent: list[dict] = []
    judge_output = json.dumps({
        "title": "Guard the parser",
        "lesson": "Check empty input before parsing.",
        "applies_when": ["parser"],
        "avoid_when": [],
        "confidence": 0.7,
    })

    def _fake_urlopen(request, *args, **kwargs):
        sent.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse({"response": judge_output})

    monkeypatch.setattr(lesson_embedding, "_open", _fake_urlopen)

    write_learning_closure(
        _qualified_op(
            problem_statement="fix the parser crash on empty input",
            terminal_outcome="FAILED",
            verifier_status="fail",
        ),
        bridge=_bridge(tmp_path),
    )

    assert sent, "judge request was not sent"
    body = sent[0]
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["options"]["num_predict"] == 768
    assert body["prompt"].startswith(
        "Respond with a single JSON object only; keys: title, lesson, applies_when"
    )
    assert "fix the parser crash on empty input" in body["prompt"]


def _capture_reflect(monkeypatch, *, with_embed: bool) -> dict:
    captured: dict = {}

    if with_embed:

        def fake(episodes, *, judge=None, model_name="", max_lessons=1, embed=None, embed_model=""):
            captured.update(episodes=episodes, embed=embed, embed_model=embed_model)
            return []

    else:

        def fake(episodes, *, judge=None, model_name="", max_lessons=1):
            captured.update(episodes=episodes)
            return []

    import nexus.learning.lessons as lessons_mod

    monkeypatch.setattr(lessons_mod, "reflect_episodes", fake)
    return captured


def test_succeeded_closure_adds_patch_excerpt(tmp_path: Path, monkeypatch) -> None:
    captured = _capture_reflect(monkeypatch, with_embed=True)
    write_learning_closure(_qualified_op(final_patch="x" * 3000), bridge=_bridge(tmp_path))
    evidence = captured["episodes"][0]["terminal_evidence"]
    assert evidence["patch_excerpt"] == "x" * 1500


def test_no_patch_excerpt_without_patch_or_success(tmp_path: Path, monkeypatch) -> None:
    captured = _capture_reflect(monkeypatch, with_embed=True)
    write_learning_closure(_qualified_op(final_patch=""), bridge=_bridge(tmp_path))
    assert "patch_excerpt" not in captured["episodes"][0]["terminal_evidence"]
    write_learning_closure(
        _qualified_op(
            terminal_outcome="FAILED", solve_eligible=False, failure_reason="verifier_fail"
        ),
        bridge=_bridge(tmp_path),
    )
    assert "patch_excerpt" not in captured["episodes"][0]["terminal_evidence"]


def test_reflect_passes_embed_when_supported(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.local_heal.lesson_embedding import embed_text

    captured = _capture_reflect(monkeypatch, with_embed=True)
    write_learning_closure(_qualified_op(), bridge=_bridge(tmp_path))
    assert captured["embed"] is embed_text
    assert captured["embed_model"]


def test_reflect_omits_embed_when_unsupported(tmp_path: Path, monkeypatch) -> None:
    captured = _capture_reflect(monkeypatch, with_embed=False)
    write_learning_closure(_qualified_op(), bridge=_bridge(tmp_path))
    assert captured["episodes"]
