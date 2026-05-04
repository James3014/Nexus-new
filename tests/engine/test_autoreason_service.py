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
    assert out["judge_count"] == 3


def test_autoreason_handles_empty_candidates():
    out = AutoreasonService().run([])

    assert out["status"] == "NO_CANDIDATES"
    assert out["winner"] is None
    assert out["stop_reason"] == "no_candidates"


def test_autoreason_candidate_factory_a_b_ab():
    svc = AutoreasonService()
    out = svc.run(
        candidates=[],
        incumbent={"summary": "incumbent patch", "score": 0.3},
        revision={"summary": "revision patch", "score": 0.5},
        synthesis={"summary": "synthesis patch with evidence", "score": 0.8, "evidence_refs": ["pytest.log"]},
        task_desc="fix bug",
        stop_threshold=2,
        judge_count=7,
    )

    assert out["status"] == "SUCCESS"
    assert out["judge_count"] == 7
    assert out["winner"] == "AB"
    assert len(out["judge_votes"]) == 7
