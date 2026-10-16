"""#2339: no benchmark answer is delivered without a model in the non-strict lane.

The 2026-10-16 zero-model proof (D1) solved 12/12 P16 tasks under a NOOP model through
hard-coded local fixers (``local_hidden_contract_fast_path``, ``local_preflight``, ``local``
after a model failure).  With those paths deleted, a NOOP model must leave every P16 fixture
unsolved: no local/hidden-contract candidate, and the winner is a model source or
``model_required_no_model_candidate`` (sprint) / ``nexus_llm_baseline_failed`` (baseline).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.app import research_flow_service
from nexus.research.sprint_service import SprintConfig, run_hyper_sprint
from scripts.bench.capability_ab_runner import _nexus_value_fixture_sources

_P16_TASKS = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "bench"
        / "public_benchmark_nexus_value_v1.json"
    ).read_text(encoding="utf-8")
)["tasks"]
_REMOVED_SOURCES = ("local_hidden_contract_fast_path", "local_preflight", "local_hidden_shadow")
_REMOVED_CODES = {
    "hidden_contract_fast_path_success",
    "hidden_contract_fast_path_miss",
    "local_preflight_before_llm_success",
    "local_preflight_before_llm_miss",
    "hidden_invariant_shadow_candidate",
}
_STRICT_ENV = (
    "NEXUS_REQUIRE_MODEL_PARTICIPATION",
    "NEXUS_MODEL_REQUIRED_EXECUTION_MODE",
    "NEXUS_SYMMETRIC_PROMPT",
    "NEXUS_BENCH_TREATMENT_LANE",
    "NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH",
    "NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM",
    "NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW",
)


class _NoopModel:
    """Stands in for the NOOP fake agy: the model is called and yields no candidate."""

    model_chain = ["noop"]
    calls = 0

    def __init__(self, *_args, **_kwargs):
        pass

    def generate(self, *_args, **_kwargs):
        type(self).calls += 1
        raise RuntimeError("noop model: no candidate")


def _non_strict_lane(monkeypatch) -> None:
    for name in _STRICT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    _NoopModel.calls = 0


def _materialize(tmp_path: Path, fixture_kind: str) -> str:
    target_code, visible_test_code, _hidden = _nexus_value_fixture_sources(fixture_kind)
    (tmp_path / "target.py").write_text(target_code, encoding="utf-8")
    (tmp_path / "test_visible.py").write_text(visible_test_code, encoding="utf-8")
    slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    slo.parent.mkdir(parents=True, exist_ok=True)
    slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8"
    )
    return target_code


def test_p16_fixture_set_is_the_contaminated_d1_set():
    ids = [task["id"] for task in _P16_TASKS]
    assert len(ids) == 12
    assert {"nexus-value-hidden-001", "nexus-value-repair-001", "nexus-value-context-001"} <= set(
        ids
    )


@pytest.mark.parametrize("task", _P16_TASKS, ids=[task["id"] for task in _P16_TASKS])
def test_noop_model_non_strict_sprint_delivers_no_local_benchmark_answer(
    monkeypatch, tmp_path: Path, task
):
    _non_strict_lane(monkeypatch)
    original = _materialize(tmp_path, task["fixture_kind"])
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", _NoopModel)

    res = run_hyper_sprint(
        repo_root=tmp_path,
        config=SprintConfig(
            task=task["task_desc"],
            target_file="target.py",
            test_file="test_visible.py",
            candidate_count=1,
            llm_mode=True,
            safe_mode=False,
        ),
    )

    assert _NoopModel.calls >= 1
    assert res.status == "FAILED"
    assert res.winner_source == "model_required_no_model_candidate" or res.winner_source.startswith(
        "llm"
    )
    assert not any(str(item.source).startswith(_REMOVED_SOURCES) for item in res.candidates)
    assert not _REMOVED_CODES & set(res.error_codes)
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == original


@pytest.mark.parametrize("task", _P16_TASKS, ids=[task["id"] for task in _P16_TASKS])
def test_noop_model_non_strict_baseline_has_no_local_fallback(monkeypatch, tmp_path: Path, task):
    _non_strict_lane(monkeypatch)
    original = _materialize(tmp_path, task["fixture_kind"])
    monkeypatch.setattr(research_flow_service, "LLMCandidateGenerator", _NoopModel)
    route = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc=task["task_desc"],
        task_type=f"public_{task['category']}",
        candidate_count=3,
        root_cause_confidence=1.0,
        findings_query=None,
        target_file="target.py",
    )
    assert route["recommended_reason"] != "benchmark_hidden_contract_fast_path"

    patched, source, meta = research_flow_service._build_baseline_patch(
        trial=0,
        original_code=original,
        task_desc=task["task_desc"],
        route=route,
        llm_baseline_required=False,
        llm_baseline=True,
        task_desc_with_codeintel=task["task_desc"],
        repo_root=tmp_path,
        task_type=f"public_{task['category']}",
        test_source="",
        target_file="target.py",
        test_file="test_visible.py",
    )

    assert _NoopModel.calls == 1
    assert source == "nexus_llm_baseline_failed"
    assert patched == original
    assert meta["baseline_source_policy"] == "llm_no_local_fallback"
    assert meta["model_patch_generated"] is False
