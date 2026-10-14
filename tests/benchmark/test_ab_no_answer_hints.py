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


# Hidden-only literals per P16 fixture from the symmetry inventory (2026-10-14, section 4).
INVENTORY_P16_LITERALS: dict[str, list[str]] = {
    "nexus-value-hidden-001": ["duplicate", "idempotent"],
    "nexus-value-hidden-002": ["API__Token", "api-token", "  User   Name  "],
    "nexus-value-repair-001": ["'timeout': None", "'jitter': 1", "ignore None", "None-valued"],
    "nexus-value-repair-002": ["remaining_ms(100, 200, 50)", "clamp", "[0, timeout"],
    "nexus-value-gov-001": ["[REDACTED]", "'password': 'pw'"],
    "nexus-value-gov-002": ["can_access('unknown'", "deny by default", "fail closed"],
    "nexus-value-evidence-001": ["'status': 'fail', 'artifact'", "singular 'artifact'"],
    "nexus-value-evidence-002": ["missing claim", "phase_ready({'status': 'pass', 'reason': ''})"],
    "nexus-value-context-001": [
        "'result': 'ok'",
        "canonical output field is result",
        "FIELD = 'result'",
    ],
    "nexus-value-context-002": ["strict=True", "retries=3", "{'strict': True, 'retries': 3}"],
    "nexus-value-trust-001": ["'evidence': 'b'}]) == 'fail'"],
    "nexus-value-trust-002": ["needs_evidence", "{'verified': False}"],
}


@pytest.fixture
def symmetric(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_NO_TASK_HINTS", "1")
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")


@pytest.mark.parametrize("task", P16_TASKS, ids=lambda t: t.id)
def test_assembled_online_prompt_is_symmetric_for_p16(task, symmetric, tmp_path: Path) -> None:
    from nexus.services.online_nexus_context import build_online_nexus_context

    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    source = Path(target_file).read_text(encoding="utf-8")
    visible = Path(visible_test_file).read_text(encoding="utf-8")
    bare_material = "\n".join([task.task_desc, source, visible])
    base_prompt = _build_llm_candidate_prompt(
        source_code=source,
        task=_nexus_task_desc(task),
        mutation_hint="baseline",
        test_source=visible,
    )
    ctx = build_online_nexus_context(
        task_statement=_nexus_task_desc(task),
        task_id=task.id,
        task_type=task.task_type,
        route={
            "fixture_kind": task.fixture_kind,
            "selected_capabilities": ["claim_gate", "delivery_gate"],
        },
        plan={"selected_capabilities": ["claim_gate", "delivery_gate", "semantic_searcher"]},
        hidden_guidance=_nexus_codex_hidden_verifier_guidance(task, source),
        source=source,
        visible_tests=visible,
        base_prompt=base_prompt,
    )
    prompt = ctx.prompt

    assert visible.strip() in prompt
    assert "[Prior Art]" not in prompt
    assert "[NEXUS VALUE CONTRACT]" not in prompt
    assert "infer hidden invariants" not in prompt
    assert ctx.guidance_pack["rules"] == []
    for literal in INVENTORY_P16_LITERALS[task.id]:
        if literal in bare_material:
            continue  # the bare arm sees it too (task text / source / visible test)
        assert literal not in prompt, f"{task.id}: with-Nexus prompt leaks {literal!r}"


def test_fixture_guidance_table_is_gone_from_the_product() -> None:
    import nexus.services.online_nexus_context as onc

    assert not hasattr(onc, "_FIXTURE_GUIDANCE")
    pack = onc.build_guidance_pack(
        selected_capabilities=[],
        task_type="repair",
        task_statement="Fix an incident classifier",
        route={"fixture_kind": "nexus_value_trust_incident_classifier"},
    )
    assert not any("needs_evidence" in rule for rule in pack["rules"])


def test_sprint_path_symmetric_prompt_gets_visible_test_and_no_memory_or_codeintel(
    symmetric, monkeypatch, tmp_path: Path
) -> None:
    from nexus.research import sprint_service
    from nexus.research.sprint_service import CandidateEval, SprintConfig, run_hyper_sprint

    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    phase_slo.parent.mkdir(parents=True, exist_ok=True)
    phase_slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8"
    )
    (tmp_path / "demo.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    visible = "from demo import value\n\ndef test_value():\n    assert value() == 2\n"
    (tmp_path / "test_demo.py").write_text(visible, encoding="utf-8")
    seen: list[dict] = []

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **kwargs):
            seen.append(dict(kwargs))
            return "def value():\n    return 2\n", {
                "source": "llm",
                "model_calls": 1,
                "tokens_used": 5,
            }

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0,
                candidate_code=kwargs["code"],
                source=kwargs["source"],
            )

    def no_codeintel(*_args, **_kwargs):
        raise AssertionError("CodeIntel repository context must not reach the symmetric prompt")

    def no_memory(*_args, **_kwargs):
        raise AssertionError("findings memory must not be read in the symmetric A/B")

    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setattr(sprint_service, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(sprint_service, "SprintExecutor", FakeExecutor)
    monkeypatch.setattr(
        "nexus.research.flow.codeintel_context.sprint_codeintel_block", no_codeintel
    )
    monkeypatch.setattr("nexus.research.findings_memory.FindingsMemoryStore.search", no_memory)

    cfg = SprintConfig(
        task="fix value",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.model_calls >= 1
    assert seen and seen[0]["test_source"].strip() == visible.strip()
    assert seen[0]["codeintel_block"] == ""


def test_strict_with_nexus_subprocess_env_disables_local_paths_and_self_heal(
    symmetric, tmp_path, monkeypatch
) -> None:
    import json
    import subprocess

    from scripts.bench.capability_ab_runner import _run_process_group as real_run_process_group
    from scripts.bench.capability_ab_runner import run_with_nexus

    task = next(t for t in P16_TASKS if t.id == "nexus-value-trust-002")
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    envs: list[dict] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            envs.append(dict(env))
            # The model's file passes the hidden test but the product reports a visible-gate FAILED.
            Path(target_file).write_text(
                "def classify(smoke_passed, semantic_evidence):\n"
                "    if not smoke_passed:\n"
                "        return 'open'\n"
                "    if isinstance(semantic_evidence, dict) and semantic_evidence.get('verified') is True:\n"
                "        return 'resolved'\n"
                "    return 'needs_evidence'\n",
                encoding="utf-8",
            )
            payload = {
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "result": {
                    "elapsed_sec": 0.1,
                    "error": "pytest_failed",
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_patch_generated": True,
                        "total_tokens": 10,
                    },
                },
            }
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return real_run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=60,
        force_flow="baseline",
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert envs
    env = envs[0]
    assert env["NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM"] == "1"
    assert env["NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH"] == "1"
    assert env["NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW"] == "1"
    assert env["NEXUS_MODEL_REQUIRED_EXECUTION_MODE"] == "model_participation_only"
    assert env["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "0"
    assert env["NEXUS_SYMMETRIC_PROMPT"] == "1"
    # S20: same gate as bare -- the hidden test on the delivered file decides.
    assert out["symmetric_hidden_only_gate"] is True
    assert out["hidden_verifier_passed"] is True
    assert out["status"] == "SUCCESS"
