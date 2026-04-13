from pathlib import Path

from nexus.research.sprint_service import (
    CandidateEval,
    InPlaceSprintExecutor,
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
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

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
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

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


def test_llm_quota_falls_back_to_local(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **_kwargs):
            raise RuntimeError("HTTP 429 quota exhausted")

    class FakeLocalGenerator:
        source = "local"

        def generate(self, **_kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.winner_source == "local"
    assert "quota" in res.error_codes
    assert "llm_fallback_local" in res.error_codes


def test_local_mode_uses_inplace_executor(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    calls = {"inplace": 0, "swarm": 0}

    class FakeLocalGenerator:
        source = "local"

        def generate(self, **_kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeInPlaceExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["inplace"] += 1

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    class FakeSwarmExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["swarm"] += 1

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeInPlaceExecutor)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeSwarmExecutor)

    cfg = SprintConfig(task="implement", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert calls["inplace"] == 1
    assert calls["swarm"] == 0


def test_inplace_executor_rejects_no_change_candidate(tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    ex = InPlaceSprintExecutor(
        repo_root=tmp_path,
        target_file="demo.py",
        pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1"],
        timeout_sec=5,
    )
    ev = ex.evaluate_candidate(seed=0, hint="h", code="print('x')\n", source="local")
    assert ev.score == 0.2
    assert ev.error == "no_change_candidate"


def test_inplace_executor_rejects_syntax_error(tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    ex = InPlaceSprintExecutor(
        repo_root=tmp_path,
        target_file="demo.py",
        pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1"],
        timeout_sec=5,
    )
    ev = ex.evaluate_candidate(seed=0, hint="h", code="def broken(:\n    pass\n", source="local")
    assert ev.score == 0.0
    assert ev.error.startswith("syntax_error:")
