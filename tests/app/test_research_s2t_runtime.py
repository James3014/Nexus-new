import json
from pathlib import Path

from nexus.app import research_flow_service
from nexus.app.research_s2t_runtime import record_autoreason_s2t_trace


def _autoreason_payload() -> dict:
    return {
        "winner": "AB",
        "borda_scores": {"A": 1, "B": 2, "AB": 4},
        "candidate_factory": {
            "candidates": [
                {
                    "candidate_id": "A",
                    "score": 0.25,
                    "summary": "baseline only",
                    "evidence_refs": ["pytest:test_a"],
                },
                {
                    "candidate_id": "B",
                    "score": 0.50,
                    "summary": "llm only",
                    "evidence_refs": ["pytest:test_b"],
                },
                {
                    "candidate_id": "AB",
                    "score": 0.95,
                    "summary": "combined verified repair",
                    "evidence_refs": ["pytest:test_ab"],
                },
            ]
        },
    }


def test_research_s2t_runtime_records_shadow_trace_payload(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_FORCE", "0")
    payload = record_autoreason_s2t_trace(
        repo_root=tmp_path,
        task_id="task-1",
        receipt_slug="receipt-1",
        autoreason_payload=_autoreason_payload(),
        result_report={
            "model_name": "gemini-3-flash",
            "model_calls": 1,
            "total_tokens": 42,
            "benchmark_split": "unit",
        },
        artifact_verified=True,
        normalized_success_criteria="pytest",
        route_decision_ref="route:task-1",
    )

    assert payload["schema_version"] == "s2t_episode.v1"
    assert payload["candidate_count"] == 3
    assert payload["selected_candidate_id"] == "AB"
    assert payload["mode"] == "shadow"
    assert payload["event"]["schema_version"] == "s2t.v1"
    assert payload["event"]["route_decision_ref"] == "route:task-1"
    assert payload["episode"]["cost"] == {"model_calls": 1, "total_tokens": 42}

    trace_path = tmp_path / payload["trace_path"]
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["candidate_set_id"] == "receipt-1:autoreason"
    assert rows[0]["selected_candidate_id"] == "AB"
    assert rows[0]["delivery_gate"] == "pass"


def test_research_flow_service_keeps_s2t_runtime_compatibility_alias():
    assert research_flow_service._record_autoreason_s2t_trace is record_autoreason_s2t_trace
