import subprocess
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TestResult:
    test_id: str
    passed: bool
    output: str

class EvaluationGate:
    """🛡️ EvaluationGate: 執行物理驗證閘門"""
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    def run_visible_tests(self, test_cmds: List[List[str]]) -> List[TestResult]:
        results = []
        for cmd in test_cmds:
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{str(self.repo_dir)}:{env.get('PYTHONPATH', '')}"
            try:
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60, env=env)
                results.append(TestResult(test_id=" ".join(cmd), passed=(res.returncode == 0), output=res.stdout + res.stderr))
            except Exception as e:
                results.append(TestResult(test_id=" ".join(cmd), passed=False, output=str(e)))
        return results

    def run_hidden_verifier(self, cmds: List[List[str]]) -> List[TestResult]:
        return []

    def get_redacted_report(self, visible: List[TestResult], hidden: List[TestResult]) -> str:
        report = "=== VISIBLE TEST REPORT ===\n"
        for r in visible:
            status = "PASS" if r.passed else "FAIL"
            report += f"[{status}] {r.test_id}\n"
        return report
