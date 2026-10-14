"""R2: in the counted like-for-like configuration the with-Nexus arm gets no answer hints.

Online A/B report 2026-10-14: the with-Nexus prompt carried hand-written decision tables
(runner ``_nexus_task_desc``) and a product prompt rule (``_build_value_task_contract``) that
restated P16 hidden assertions; the bare arm got only ``task.task_desc``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nexus.research.sprint_service import _build_llm_candidate_prompt
from scripts.bench.capability_ab_runner import (
    _hidden_test_for_visible_test,
    _materialize_fixture,
    _nexus_codex_hidden_verifier_guidance,
    _nexus_task_desc,
    load_tasks,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
P16_TASKS = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")

# Hidden-contract facts per P16 fixture, phrased the way the removed hints phrased them.
HIDDEN_FACTS: dict[str, list[str]] = {
    "nexus-value-context-001": ["canonical output field is result", "FIELD = 'result'"],
    "nexus-value-context-002": ["retries=3", "'retries': 3", "strict=True and"],
    "nexus-value-trust-002": ["needs_evidence"],
    "nexus-value-hidden-002": [
        "Collapse repeated separators",
        "underscores as separators",
        "api-token",
    ],
    "nexus-value-repair-001": [
        "override value is None",
        "whose value is None",
        "must not mutate defaults",
    ],
    "nexus-value-repair-002": [
        "clamped to the inclusive range",
        "Return 0 when elapsed",
        "[0, timeout",
    ],
    "nexus-value-evidence-001": ["claim ids that satisfy", "non-empty string"],
    "nexus-value-evidence-002": [
        "failing phases require a non-empty reason",
        "Passing phases require evidence",
    ],
    "nexus-value-gov-001": ["[REDACTED]"],
}


def _literals(source: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
            out.add(node.value.strip())
    return out


def _hidden_assert_lines(hidden: str, visible: str) -> list[str]:
    visible_lines = {line.strip() for line in visible.splitlines()}
    return [
        line.strip()
        for line in hidden.splitlines()
        if line.strip().startswith("assert ")
        and line.strip() not in visible_lines
        and "_SPEC" not in line
    ]


@pytest.fixture
def no_hints(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_NO_TASK_HINTS", "1")
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")


def test_p16_task_list_is_the_twelve_value_tasks() -> None:
    assert len(P16_TASKS) == 12
    assert set(HIDDEN_FACTS) <= {task.id for task in P16_TASKS}


@pytest.mark.parametrize("task", P16_TASKS, ids=lambda t: t.id)
def test_strict_with_nexus_task_text_equals_bare_task_text(task, no_hints) -> None:
    assert _nexus_task_desc(task) == task.task_desc


@pytest.mark.parametrize("task", P16_TASKS, ids=lambda t: t.id)
def test_with_nexus_prompt_contains_no_p16_hidden_assertion(task, no_hints, tmp_path: Path) -> None:
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    source = Path(target_file).read_text(encoding="utf-8")
    visible = Path(visible_test_file).read_text(encoding="utf-8")
    hidden = Path(_hidden_test_for_visible_test(visible_test_file)).read_text(encoding="utf-8")
    bare_material = "\n".join([task.task_desc, source, visible])

    task_text = _nexus_task_desc(task)
    prompts = [
        _build_llm_candidate_prompt(
            source_code=source, task=task_text, mutation_hint="baseline", test_source=""
        ),
        _build_llm_candidate_prompt(
            source_code=source, task=task_text, mutation_hint="baseline", test_source=visible
        ),
        _nexus_codex_hidden_verifier_guidance(task, source),
    ]

    # Literal hidden-only answers: string constants of the hidden test the bare arm never sees.
    hidden_only = sorted(
        literal
        for literal in _literals(hidden) - _literals(visible)
        if len(literal) >= 4 and literal not in bare_material
    )
    facts = [*HIDDEN_FACTS.get(task.id, []), *hidden_only, *_hidden_assert_lines(hidden, visible)]
    for fact in facts:
        assert fact not in bare_material or fact in hidden_only, (
            f"{task.id}: {fact!r} is visible to bare; fix the table"
        )
        for prompt in prompts:
            assert fact not in prompt, f"{task.id}: with-Nexus prompt leaks hidden fact {fact!r}"
