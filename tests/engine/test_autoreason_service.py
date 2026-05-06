from nexus.engine.autoreason_service import AutoreasonService


class FakeSemanticJudge:
    name = "fake_semantic"

    def rank(self, *, task_desc, candidates):
        return {
            "judge": self.name,
            "ranking": ["b", "a"],
            "reason": "semantic_evidence_matches_failure",
            "rubric": {
                "correctness": 0.95,
                "regression_risk": 0.1,
                "evidence_quality": 0.9,
                "minimality": 0.8,
                "semantic_fit": 0.95,
            },
        }


class FailingSemanticJudge:
    name = "failing_semantic"

    def rank(self, *, task_desc, candidates):
        raise RuntimeError("provider unavailable")


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
    assert out["enabled"] is True
    assert out["status"] == "SUCCESS"
    assert out["winner"] == "b"
    assert out["stop_reason"] == "a_streak_met"
    assert len(out["judge_votes"]) == 3
    assert out["judge_count"] == 3
    assert out["judge_mode"] == "deterministic_evidence_quality"
    assert out["semantic_judged"] is False
    assert "rubric" in out["judge_votes"][0]


def test_autoreason_handles_empty_candidates():
    out = AutoreasonService().run([])

    assert out["status"] == "NO_CANDIDATES"
    assert out["enabled"] is False
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
    assert out["winner_role"] == "AB"
    assert len(out["judge_votes"]) == 7


def test_autoreason_candidate_factory_from_summaries_emits_a_b_ab_contract():
    svc = AutoreasonService()
    factory = svc.candidate_factory_from_summaries(
        [
            {"candidate_id": "baseline", "hint": "stable but incomplete", "score": 0.4, "stdout_excerpt": "old tests pass"},
            {"candidate_id": "patch", "hint": "fixes edge case with tests", "score": 0.8, "stdout_excerpt": "new tests pass"},
        ],
        task_desc="fix edge case",
    )

    assert factory["schema"] == "nexus_autoreason_candidate_factory_v1"
    assert factory["status"] == "READY"
    assert factory["candidate_roles"] == {"A": "A", "B": "B", "AB": "AB"}

    out = svc.run(candidates=factory["candidates"], task_desc="fix edge case", judge_count=7)

    assert out["winner"] == "AB"


def test_autoreason_semantic_judge_can_beat_evidence_count_heuristic():
    out = AutoreasonService(judge_providers=[FakeSemanticJudge()]).run(
        [
            {
                "candidate_id": "a",
                "summary": "long patch with many generic logs",
                "score": 0.8,
                "evidence_refs": ["log1", "log2", "log3", "log4"],
            },
            {
                "candidate_id": "b",
                "summary": "fixes timeout race with targeted regression test",
                "score": 0.6,
                "evidence_refs": ["tests/test_timeout.py::test_race"],
            },
        ],
        task_desc="fix timeout race without regression",
        stop_threshold=1,
        judge_count=3,
    )

    assert out["winner"] == "b"
    assert out["judge_mode"] == "semantic"
    assert out["semantic_judged"] is True
    assert out["judge_votes"][0]["rubric"]["semantic_fit"] == 0.95


def test_autoreason_falls_back_when_semantic_provider_unavailable():
    out = AutoreasonService(judge_providers=[FailingSemanticJudge()]).run(
        [
            {"candidate_id": "a", "summary": "generic log", "score": 0.9, "evidence_refs": ["log1", "log2"]},
            {"candidate_id": "b", "summary": "targeted regression test", "score": 0.6, "evidence_refs": ["pytest passed"]},
        ],
        task_desc="fix regression",
        stop_threshold=2,
    )

    assert out["status"] == "SUCCESS"
    assert out["judge_mode"] == "deterministic_evidence_quality"
    assert out["semantic_judged"] is False


def test_autoreason_deterministic_judge_prefers_quality_over_evidence_count():
    out = AutoreasonService().run(
        [
            {
                "candidate_id": "noisy",
                "summary": "generic patch with many logs but unclear risk",
                "score": 0.8,
                "evidence_refs": ["log1", "log2", "log3", "log4", "log5"],
            },
            {
                "candidate_id": "targeted",
                "summary": "fix timeout race boundary with regression test",
                "score": 0.55,
                "evidence_refs": ["tests/test_timeout.py::test_race passed"],
            },
        ],
        task_desc="fix timeout race without regression",
        stop_threshold=2,
        judge_count=3,
    )

    assert out["winner"] == "targeted"
    assert out["judge_mode"] == "deterministic_evidence_quality"
    assert all(vote["ranking"][0] == "targeted" for vote in out["judge_votes"])
