from nexus.engine.autoreason_service import AutoreasonService


def test_autoreason_selects_evidence_backed_candidate():
    out = AutoreasonService().run(
        [
            {"candidate_id": "a", "summary": "short", "score": 0.9},
            {"candidate_id": "b", "summary": "specific repair with tests", "score": 0.7, "evidence_refs": ["pytest.log"]},
        ],
        task_desc="fix bug",
        stop_threshold=2,
    )

    assert out["schema"] == "nexus_autoreason_result_v1"
    assert out["status"] == "SUCCESS"
    assert out["winner"] == "b"
    assert out["stop_reason"] == "a_streak_met"
    assert len(out["judge_votes"]) == 3


def test_autoreason_handles_empty_candidates():
    out = AutoreasonService().run([])

    assert out["status"] == "NO_CANDIDATES"
    assert out["winner"] is None
    assert out["stop_reason"] == "no_candidates"
