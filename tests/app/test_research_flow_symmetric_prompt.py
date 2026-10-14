"""Like-for-like A/B (``NEXUS_SYMMETRIC_PROMPT``) on the auto-flow baseline path.

Symmetry inventory 2026-10-14: S4 (visible test withheld from the with-Nexus model), S5 (prior
art from earlier tasks/trials injected), S6 (CodeIntel repository context injected), S20 (the
model's file is discarded when the visible test fails, so the hidden verifier never sees it).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from nexus.app import research_flow_service

ORIGINAL = "def value():\n    return 1\n"
MODEL_PATCH = "def value():\n    return 2\n"
VISIBLE_TEST = "from demo import value\n\ndef test_value():\n    assert value() == 3\n"


class _FakeLearnMode:
    def __init__(self, *_args, **_kwargs):
        pass

    def ask(self, **_kwargs):
        return {"citations": [{"claim": "PRIOR-ART-FROM-AN-EARLIER-TRIAL"}]}


def _run(
    tmp_path: Path,
    monkeypatch,
    *,
    symmetric: bool,
    force_flow: str = "baseline",
    sprint_calls: list | None = None,
) -> tuple[dict, list[dict]]:
    (tmp_path / "demo.py").write_text(ORIGINAL, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(VISIBLE_TEST, encoding="utf-8")
    calls: list[dict] = []

    class FakeLLMGenerator:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **kwargs):
            calls.append(dict(kwargs))
            return MODEL_PATCH, {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
            }

    if symmetric:
        monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    else:
        monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    monkeypatch.setattr(research_flow_service, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.learn_mode.LearnModeService", _FakeLearnMode)
    monkeypatch.setattr(
        research_flow_service,
        "_build_codeintel_evidence",
        lambda *_a, **_k: {
            "status": "ok",
            "impact_report": "upstream/fixed_code_impact.json",
            "risk_score": 1,
        },
    )
    monkeypatch.setattr(
        research_flow_service.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr="assertion failed"
        ),
    )
    if sprint_calls is not None:
        from nexus.research.sprint_service import SprintResult

        def fake_run_hyper_sprint(*, repo_root, config):
            sprint_calls.append(config)
            return SprintResult(
                status="FAILED",
                reason="stage1_no_passing_candidate",
                target_file=config.target_file,
                winner_source="llm",
                final_score=0.0,
                elapsed_sec=0.1,
                attempt_count=1,
                model_calls=1,
                quota_backoffs=0,
                test_timeouts=0,
                patch=MODEL_PATCH,
            )

        monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_run_hyper_sprint)
    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix value bug",
        target_file="demo.py",
        test_file="test_demo.py",
        task_type="bug",
        candidate_count=1,
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
        force_flow=force_flow,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id="case-symmetric-baseline",
    )
    return payload, calls


def test_symmetric_baseline_prompt_has_visible_test_and_no_prior_art_or_codeintel(
    tmp_path: Path, monkeypatch
):
    _payload, calls = _run(tmp_path, monkeypatch, symmetric=True)

    assert calls, "the model must be called"
    for call in calls:
        assert call.get("test_source") == VISIBLE_TEST
        assert "[Prior Art]" not in call["task"]
        assert "PRIOR-ART-FROM-AN-EARLIER-TRIAL" not in call["task"]
        assert "[Nexus CodeIntel" not in call["task"]
        assert call["task"] == "Fix value bug"


def test_symmetric_baseline_keeps_model_file_for_hidden_verification(tmp_path: Path, monkeypatch):
    payload, _ = _run(tmp_path, monkeypatch, symmetric=True)

    # The product still reports the visible-test failure, but the model's file stays delivered so
    # the bench judges it with the hidden test only, exactly like the bare arm.
    assert payload["result"]["status"] == "FAILED"
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == MODEL_PATCH


def test_non_symmetric_baseline_behaviour_is_unchanged(tmp_path: Path, monkeypatch):
    payload, calls = _run(tmp_path, monkeypatch, symmetric=False)

    assert payload["result"]["status"] == "FAILED"
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == ORIGINAL
    assert calls and "[Prior Art]" in calls[0]["task"]


def test_symmetric_hyper_sprint_delivers_model_file_with_one_model_call(
    tmp_path: Path, monkeypatch
):
    """H1 / P1-1 / L3 on the hyper path (the counted lane forces hyper_sprint)."""

    sprint_calls: list = []
    payload, baseline_calls = _run(
        tmp_path, monkeypatch, symmetric=True, force_flow="hyper_sprint", sprint_calls=sprint_calls
    )
    report = payload["result"]["report"]
    assert payload["result"]["status"] == "FAILED"
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == MODEL_PATCH
    assert report["symmetric_model_delivery"] is True
    import hashlib

    assert report["model_candidate_sha256"] == hashlib.sha256(MODEL_PATCH.encode()).hexdigest()
    # Exactly one model attempt: no baseline probe, one hyper candidate, one round.
    assert baseline_calls == []
    assert len(sprint_calls) == 1
    assert sprint_calls[0].candidate_count == 1 and sprint_calls[0].max_rounds == 1


def test_non_symmetric_hyper_sprint_does_not_write_a_failed_patch(tmp_path: Path, monkeypatch):
    sprint_calls: list = []
    payload, _ = _run(
        tmp_path, monkeypatch, symmetric=False, force_flow="hyper_sprint", sprint_calls=sprint_calls
    )
    assert payload["result"]["status"] == "FAILED"
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == ORIGINAL
    assert "model_candidate_sha256" not in payload["result"]["report"]
