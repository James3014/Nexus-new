import pytest
from pathlib import Path
from nexus.research.evaluation.candidate_evaluator import CandidateEvaluator
from nexus.research.evaluation.eval_models import EvalErrorCode

def test_evaluator_detects_no_change(tmp_path: Path):
    evaluator = CandidateEvaluator(tmp_path, ["pytest"], 10)
    code = "print('ok')"
    res = evaluator.evaluate(seed=0, hint="test", code=code, source="test", target_file="demo.py", original_code=code)
    assert res.error == EvalErrorCode.NO_CHANGE
    assert res.score == 0.2

def test_evaluator_detects_syntax_error(tmp_path: Path):
    evaluator = CandidateEvaluator(tmp_path, ["pytest"], 10)
    code = "print('missing quote"
    res = evaluator.evaluate(seed=0, hint="test", code=code, source="test", target_file="demo.py", original_code="print('ok')")
    assert 'syntax_error' in res.error.lower()
    assert res.score == 0.0

def test_evaluator_handles_timeout(tmp_path: Path, monkeypatch):
    import subprocess
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)
    
    import nexus.research.evaluation.candidate_evaluator
    monkeypatch.setattr(nexus.research.evaluation.candidate_evaluator.subprocess, "run", fake_run)
    
    evaluator = CandidateEvaluator(tmp_path, ["pytest"], 1)
    res = evaluator.evaluate(seed=0, hint="test", code="print('ok')", source="test", target_file="demo.py", original_code="print('old')")
    assert res.error_codes == [EvalErrorCode.TEST_TIMEOUT]
