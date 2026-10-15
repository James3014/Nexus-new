"""Wiring plan PR-3: the auto-flow side of the online A/B treatment lane.

The strict lane (``NEXUS_SYMMETRIC_PROMPT`` alone) forces one hyper candidate and one round. The
treatment lane (``NEXUS_BENCH_TREATMENT_LANE=1`` on top of the symmetric prompt) keeps the profile
counts (capped by ``NEXUS_LLM_CANDIDATE_CAP``) and delivers the self-heal output, but only when the
delivered patch is byte-identical to one of the sprint's recorded raw model candidates.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from nexus.app import research_flow_service

ORIGINAL = "def value():\n    return 1\n"
FIRST = "def value():\n    return 3\n"
REPAIR = "def value():\n    return 2\n"
VISIBLE_TEST = "from demo import value\n\ndef test_value():\n    assert value() == 2\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run(
    tmp_path: Path,
    monkeypatch,
    *,
    treatment: bool,
    candidate_count: int = 3,
    winner: str = "llm_self_heal",
    patch: str = REPAIR,
    recorded: tuple[str, ...] = (FIRST, REPAIR),
) -> tuple[dict, list]:
    from nexus.research.sprint_service import SprintResult

    (tmp_path / "demo.py").write_text(ORIGINAL, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(VISIBLE_TEST, encoding="utf-8")
    sprint_calls: list = []

    class NoBaseline:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **_kwargs):
            raise AssertionError("the forced hyper flow makes no baseline call")

    def fake_run_hyper_sprint(*, repo_root, config):
        sprint_calls.append(config)
        return SprintResult(
            status="FAILED",
            reason="stage1_no_passing_candidate",
            target_file=config.target_file,
            winner_source=winner,
            final_score=0.0,
            elapsed_sec=0.1,
            attempt_count=len(recorded),
            model_calls=len(recorded),
            quota_backoffs=0,
            test_timeouts=0,
            patch=patch,
            learning_trace={
                "model_candidate_sha256": _sha(recorded[0]),
                "model_candidate_sha256s": [_sha(code) for code in recorded],
                "model_candidate_sources": ["llm", *["llm_self_heal"] * (len(recorded) - 1)],
            },
        )

    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.setenv("NEXUS_LLM_CANDIDATE_CAP", "4")
    if treatment:
        monkeypatch.setenv("NEXUS_BENCH_TREATMENT_LANE", "1")
    else:
        monkeypatch.delenv("NEXUS_BENCH_TREATMENT_LANE", raising=False)
    monkeypatch.setattr(research_flow_service, "LLMCandidateGenerator", NoBaseline)
    monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_run_hyper_sprint)
    monkeypatch.setattr(
        research_flow_service, "_build_codeintel_evidence", lambda *_a, **_k: {"status": "ok"}
    )
    monkeypatch.setattr(
        research_flow_service.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="", stderr="failed"),
    )
    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix value bug",
        target_file="demo.py",
        test_file="test_demo.py",
        task_type="bug",
        candidate_count=candidate_count,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=True,
        llm_baseline=True,
        llm_baseline_required=True,
        timeout_sec=30,
        stage1_timeout_sec=10,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=0.0,
        history_window=1,
        history_fail_threshold=999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=1,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id="case-treatment-lane",
    )
    return payload, sprint_calls


def test_self_heal_source_is_a_model_source_only_in_the_treatment_lane(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.delenv("NEXUS_BENCH_TREATMENT_LANE", raising=False)
    assert research_flow_service._is_symmetric_model_source("llm") is True
    assert research_flow_service._is_symmetric_model_source("llm_self_heal") is False
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_LANE", "1")
    assert research_flow_service._is_symmetric_model_source("llm_self_heal") is True
    assert research_flow_service._is_symmetric_model_source("local_hidden_shadow") is False
    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT")
    assert research_flow_service._is_symmetric_model_source("llm_self_heal") is False


def test_strict_lane_keeps_one_candidate_and_one_round(tmp_path: Path, monkeypatch) -> None:
    payload, calls = _run(tmp_path, monkeypatch, treatment=False)
    assert calls and calls[0].candidate_count == 1 and calls[0].max_rounds == 1
    # the self-heal output is never delivered in the strict lane
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == ORIGINAL
    assert "model_candidate_sha256" not in payload["result"]["report"]


def test_treatment_lane_uses_profile_counts_and_delivers_the_bound_self_heal(
    tmp_path: Path, monkeypatch
) -> None:
    payload, calls = _run(tmp_path, monkeypatch, treatment=True)
    assert calls and calls[0].candidate_count == 3  # requested 3, capped at 4
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == REPAIR
    report = payload["result"]["report"]
    assert report["model_candidate_sha256"] == _sha(REPAIR)
    assert report["symmetric_model_delivery"] is True


def test_treatment_lane_never_delivers_a_patch_outside_the_model_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    payload, _ = _run(tmp_path, monkeypatch, treatment=True, patch=REPAIR + "# post-processed\n")
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == ORIGINAL
    assert "model_candidate_sha256" not in payload["result"]["report"]


def test_treatment_lane_never_delivers_a_local_winner(tmp_path: Path, monkeypatch) -> None:
    payload, _ = _run(tmp_path, monkeypatch, treatment=True, winner="local_guard_fallback")
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == ORIGINAL
    assert "model_candidate_sha256" not in payload["result"]["report"]
