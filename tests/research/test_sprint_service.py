from pathlib import Path

from nexus.research.sprint_service import (
    CandidateEval,
    SprintConfig,
    run_hyper_sprint,
    write_sprint_report,
)


def test_run_hyper_sprint_success_local(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "local"

        def generate(self, **_kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="implement", target_file="demo.py", candidate_count=2, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.winner_source == "local"
    assert res.model_calls == 0
    assert res.promotable is True
    assert res.attempt_count == 1


def test_run_hyper_sprint_collects_error_codes(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "local"

        def generate(self, **_kwargs):
            return "print('x')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(
                seed=kwargs["seed"],
                score=0.0,
                candidate_code="print('x')\n",
                source=kwargs["source"],
                error="command timed out after 20 seconds",
            )

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "FAILED"
    assert "test_timeout" in res.error_codes
    assert "stage1_failed" in res.error_codes


def test_write_sprint_report(tmp_path: Path):
    target = tmp_path / "x.py"
    target.write_text("print('x')\n", encoding="utf-8")
    cfg = SprintConfig(task="x", target_file="x.py")
    # minimal run path with monkeypatch-free failure due to missing swarm dirs still yields reportable result
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    report_path = write_sprint_report(repo_root=tmp_path, result=res, report_file=".nexus/reports/research/sprint-test.json")
    assert report_path.exists()
    assert "sprint-test.json" in str(report_path)
