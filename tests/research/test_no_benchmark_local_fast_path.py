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


# #2339 follow-up (PR-5c-2): the local answer table must not reach a model prompt, ride along as
# companion edits, or be delivered when the model baseline is skipped.
_SUPPORT_HEADER = "[NEXUS LOCAL SUPPORT CANDIDATE]"


@pytest.mark.parametrize("task", _P16_TASKS, ids=[task["id"] for task in _P16_TASKS])
def test_echo_model_under_model_participation_never_sees_local_answer(
    monkeypatch, tmp_path: Path, task
):
    """An echo model returns whatever local code a prompt hands it (support block or source)."""
    _non_strict_lane(monkeypatch)
    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    original = _materialize(tmp_path, task["fixture_kind"])
    prompts: list[dict[str, str]] = []

    class EchoModel:
        model_chain = ["echo"]

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *, source_code, task, mutation_hint="", seed=0, **_kwargs):
            prompts.append({"source_code": source_code, "task": task})
            if _SUPPORT_HEADER in task:
                return task.split(_SUPPORT_HEADER, 1)[1].split("\n", 2)[2], {
                    "source": "llm",
                    "model_calls": 1,
                }
            return source_code, {"source": "llm", "model_calls": 1}

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", EchoModel)
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

    assert prompts
    assert not any(_SUPPORT_HEADER in item["task"] for item in prompts)
    assert all(item["source_code"] == original for item in prompts)
    assert "model_required_local_support_hint" not in res.error_codes
    assert res.status == "FAILED"


@pytest.mark.parametrize("task", _P16_TASKS, ids=[task["id"] for task in _P16_TASKS])
def test_model_run_with_skipped_baseline_delivers_no_local_answer(
    monkeypatch, tmp_path: Path, task
):
    """Route-cost ``skip_llm_baseline``: llm_mode on, model baseline off, NOOP model."""
    _non_strict_lane(monkeypatch)
    original = _materialize(tmp_path, task["fixture_kind"])
    monkeypatch.setattr(research_flow_service, "LLMCandidateGenerator", _NoopModel)
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", _NoopModel)

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc=task["task_desc"],
        target_file=str(tmp_path / "target.py"),
        test_file=str(tmp_path / "test_visible.py"),
        task_type=f"public_{task['category']}",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=True,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=10,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=0.0,
        history_window=1,
        history_fail_threshold=999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=1,
        force_flow=None,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id=f"skip-baseline-{task['id']}",
    )

    report = payload["result"].get("report") or {}
    assert payload["result"]["status"] != "SUCCESS"
    assert not str(report.get("source") or report.get("winner_source") or "").startswith("local")
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == original


def test_model_baseline_patch_is_delivered_without_local_companion_edits(
    monkeypatch, tmp_path: Path
):
    """The pricing fixture has a fixture-keyed companion edit (tax.py) in the local mutator."""
    _non_strict_lane(monkeypatch)
    invoice = tmp_path / "invoice.py"
    tax = tmp_path / "tax.py"
    invoice.write_text(
        "from tax import tax_for\n\n\ndef total(subtotal):\n    return subtotal\n", encoding="utf-8"
    )
    tax_source = "def tax_for(subtotal):\n    return 0\n"
    tax.write_text(tax_source, encoding="utf-8")
    test_file = tmp_path / "test_invoice.py"
    test_file.write_text(
        "import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from invoice import total  # noqa: E402\n\n\ndef test_total_includes_tax():\n    assert total(100) == 108\n",
        encoding="utf-8",
    )
    model_patch = "from tax import tax_for\n\n\ndef total(subtotal):\n    return subtotal + tax_for(subtotal)\n"

    class InvoiceOnlyModel:
        model_chain = ["invoice-only"]

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *_args, **_kwargs):
            return model_patch, {"source": "llm", "model_calls": 1, "model_patch_generated": True}

    monkeypatch.setattr(research_flow_service, "LLMCandidateGenerator", InvoiceOnlyModel)
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", InvoiceOnlyModel)

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Refactor invoice pricing so tax lives in a shared place and total includes tax.",
        target_file=str(invoice),
        test_file=str(test_file),
        task_type="public_refactor",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=True,
        llm_baseline=True,
        timeout_sec=30,
        stage1_timeout_sec=10,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=0.0,
        history_window=1,
        history_fail_threshold=999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=1,
        force_flow="baseline",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id="companion-edit",
    )

    # The model's invoice.py alone does not pass (tax_for still returns 0); the local mutator's
    # tax.py companion edit must not be written to make it pass.
    assert tax.read_text(encoding="utf-8") == tax_source
    assert payload["result"]["status"] != "SUCCESS"
