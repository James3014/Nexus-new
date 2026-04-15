from __future__ import annotations
import time
import subprocess
from pathlib import Path
from typing import Any, List, Optional
import sys

from .eval_models import CandidateEvalResult, EvalErrorCode

class CandidateEvaluator:
    def __init__(self, repo_root: Path, pytest_cmd: List[str], timeout_sec: int):
        self.repo_root = repo_root
        self.pytest_cmd = pytest_cmd
        self.timeout_sec = timeout_sec

    def evaluate(self, *, seed: int, hint: str, code: str, source: str, target_file: str, original_code: str) -> CandidateEvalResult:
        start = time.time()
        res = CandidateEvalResult(seed=seed, hint=hint, source=source, candidate_code=code)
        
        try:
            # 1. Syntax Check
            if code == original_code:
                res.score = 0.2
                res.error = EvalErrorCode.NO_CHANGE
                res.error_codes = [EvalErrorCode.NO_CHANGE]
                res.elapsed_sec = round(time.time() - start, 4)
                return res

            if target_file.endswith(".py"):
                try:
                    compile(code, target_file, "exec")
                except SyntaxError as exc:
                    res.score = 0.0
                    res.error = f"{EvalErrorCode.SYNTAX_ERROR.value}:{exc.msg}"
                    res.error_codes = [EvalErrorCode.SYNTAX_ERROR]
                    res.elapsed_sec = round(time.time() - start, 4)
                    return res

            # 2. Test Run (Timeout Guarded)
            target_path = self.repo_root / target_file
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code, encoding="utf-8")
            
            try:
                # Use sys.executable -m pytest optimization from P0
                p_cmd = list(self.pytest_cmd)
                if p_cmd[0] == "uv" and p_cmd[1] == "run":
                    p_cmd = [sys.executable, "-m"] + p_cmd[2:]
                
                run_res = subprocess.run(
                    p_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                    cwd=self.repo_root,
                )
                res.ok = run_res.returncode == 0
                res.status = "SUCCESS" if res.ok else "FAILED"
                res.score = 1.0 if res.ok else 0.4
                res.stdout = run_res.stdout
                res.stderr = run_res.stderr
                if not res.ok:
                    res.error_codes = [EvalErrorCode.TEST_FAILED]

            except subprocess.TimeoutExpired as exc:
                res.score = 0.0
                res.error = str(exc)
                res.error_codes = [EvalErrorCode.TEST_TIMEOUT]
            
            finally:
                # Restore original
                if original_code is not None:
                    target_path.write_text(original_code, encoding="utf-8")

        except Exception as exc:
            res.score = 0.0
            res.error = str(exc)
            res.error_codes = [EvalErrorCode.UNKNOWN_ERROR]
            
        res.elapsed_sec = round(time.time() - start, 4)
        return res
