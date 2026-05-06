from __future__ import annotations

from nexus.app.research_autoreason_runtime import build_autoreason_payload


def test_build_autoreason_payload_runs_candidate_factory_tournament():
    payload = build_autoreason_payload(
        result={"flow": "hyper_sprint"},
        result_report={
            "candidate_summaries": [
                {"candidate_id": "one", "hint": "baseline keeps race", "stdout_excerpt": "pytest failed", "score": 0.2},
                {"candidate_id": "two", "hint": "fixes timeout race", "stdout_excerpt": "pytest passed", "score": 0.9},
            ]
        },
        hyper_learning_trace={},
        route={"capability_stack": {"selected_capabilities": ["hyper_sprint", "autoreason"], "stop_policy": {"threshold": 2}}},
        task_desc="Fix flaky websocket timeout race",
    )

    assert payload["status"] == "SUCCESS"
    assert payload["enabled"] is True
    assert payload["winner"] == "AB"
    assert payload["candidate_factory"]["status"] == "READY"
    assert payload["semantic_judged"] is False
    assert payload["judge_mode"] == "deterministic_evidence_quality"


def test_build_autoreason_payload_uses_opt_in_semantic_provider(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_JUDGE_PROVIDERS", "fake")

    payload = build_autoreason_payload(
        result={"flow": "hyper_sprint"},
        result_report={
            "candidate_summaries": [
                {"candidate_id": "one", "hint": "baseline keeps race", "stdout_excerpt": "pytest failed", "score": 0.2},
                {"candidate_id": "two", "hint": "fixes timeout race", "stdout_excerpt": "pytest passed", "score": 0.9},
            ]
        },
        hyper_learning_trace={},
        route={"route_decision": {"executor_controls": {"enable_autoreason_executor": True}}},
        task_desc="Fix flaky websocket timeout race",
    )

    assert payload["status"] == "SUCCESS"
    assert payload["semantic_judged"] is True
    assert payload["judge_mode"] == "semantic"


def test_build_autoreason_payload_skips_without_summaries():
    payload = build_autoreason_payload(
        result={"flow": "hyper_sprint"},
        result_report={},
        hyper_learning_trace={},
        route={},
        task_desc="Fix simple bug",
    )

    assert payload["status"] == "SKIPPED"
    assert payload["stop_reason"] == "candidate_summaries_missing"


def test_build_autoreason_payload_skips_when_factory_has_single_candidate():
    payload = build_autoreason_payload(
        result={"flow": "hyper_sprint"},
        result_report={"candidate_summaries": [{"candidate_id": "one", "hint": "only candidate", "score": 0.4}]},
        hyper_learning_trace={},
        route={"capability_plan": {"selected_capabilities": ["autoreason"]}},
        task_desc="Fix simple bug",
    )

    assert payload["status"] == "SKIPPED"
    assert payload["stop_reason"] == "candidate_factory_skipped"
    assert payload["candidate_factory"]["reason"] == "insufficient_candidate_summaries"


def test_build_autoreason_payload_preserves_existing_trace_when_not_rerunnable():
    existing = {"schema": "nexus_autoreason_result_v1", "status": "SUCCESS", "winner": "B", "enabled": True}

    payload = build_autoreason_payload(
        result={"flow": "baseline"},
        result_report={},
        hyper_learning_trace={"autoreason": existing},
        route={},
        task_desc="Fix simple bug",
    )

    assert payload == existing


def test_build_autoreason_payload_skips_when_route_did_not_select_autoreason():
    payload = build_autoreason_payload(
        result={"flow": "hyper_sprint"},
        result_report={
            "candidate_summaries": [
                {"candidate_id": "one", "hint": "baseline keeps race", "stdout_excerpt": "pytest failed", "score": 0.2},
                {"candidate_id": "two", "hint": "fixes timeout race", "stdout_excerpt": "pytest passed", "score": 0.9},
            ]
        },
        hyper_learning_trace={},
        route={"capability_stack": {"selected_capabilities": ["hyper_sprint"]}},
        task_desc="Fix flaky websocket timeout race",
    )

    assert payload["status"] == "SKIPPED"
    assert payload["enabled"] is False
    assert payload["stop_reason"] == "route_autoreason_disabled"
