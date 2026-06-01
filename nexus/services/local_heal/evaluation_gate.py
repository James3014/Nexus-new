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
    is_hidden: bool = False

class EvaluationGate:
    """🛡️ EvaluationGate: 執行物理驗證閘門"""
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    def run_visible_tests(self, test_cmds: List[List[str]]) -> List[TestResult]:
        results = []
        for cmd in test_cmds:
            env = os.environ.copy()
            benchmarks_dir = str(self.repo_dir / "scripts/benchmarks")
            env["PYTHONPATH"] = f"{str(self.repo_dir)}:{benchmarks_dir}:{env.get('PYTHONPATH', '')}"
            try:
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60, env=env)
                results.append(TestResult(test_id=" ".join(cmd), passed=(res.returncode == 0), output=res.stdout + res.stderr))
            except Exception as e:
                results.append(TestResult(test_id=" ".join(cmd), passed=False, output=str(e)))
        return results

    def run_hidden_verifier(self, cmds: List[List[str]]) -> List[TestResult]:
        if not cmds:
            return [TestResult(
                test_id="hidden_verifier_configured",
                passed=False,
                output="Hidden verifier required but no verifier command was configured.",
                is_hidden=True,
            )]
        results = []
        for cmd in cmds:
            env = os.environ.copy()
            benchmarks_dir = str(self.repo_dir / "scripts/benchmarks")
            env["PYTHONPATH"] = f"{str(self.repo_dir)}:{benchmarks_dir}:{env.get('PYTHONPATH', '')}"
            try:
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60, env=env)
                results.append(TestResult(test_id=" ".join(cmd), passed=(res.returncode == 0), output=res.stdout + res.stderr, is_hidden=True))
            except Exception as e:
                results.append(TestResult(test_id=" ".join(cmd), passed=False, output=str(e), is_hidden=True))
        return results

    def get_redacted_report(self, visible: List[TestResult], hidden: List[TestResult]) -> str:
        report = "=== VISIBLE TEST REPORT ===\n"
        for r in visible:
            status = "PASS" if r.passed else "FAIL"
            report += f"[{status}] {r.test_id}\n"
            if not r.passed and r.output:
                report += f"{r.output[-500:]}\n"
        report += "\n=== HIDDEN VERIFIER STATUS ===\n"
        if not hidden:
            report += "[NOT_CONFIGURED] Hidden verifier was not requested.\n"
        else:
            failed = [r for r in hidden if not r.passed]
            if failed:
                report += f"[FAIL] {len(failed)} hidden verifier(s) failed. Details redacted.\n"
            else:
                report += "[PASS] All hidden verifiers passed.\n"
        return report
