"""
Evidence Verifier: 系統級獨立驗證器。
不依賴 Agent 自述，透過物理命令獨立產生/驗證 evidence。
"""

import subprocess
from pathlib import Path
from typing import Any, List

from .anti_drift import AntiDrift
from .replay_runner import ReplayRunner, check_pytest_args, split_command

# Test commands in agent-written evidence are data, never shell text (#2634).
# Only these test-runner prefixes are executed, argv-only and without a shell;
# their options pass the shared pytest option allowlist and positional paths must
# resolve inside the project root.  Anything else is recorded as UNCOVERED
# (advisory, not executed).  A project-relative interpreter such as
# ``.venv/bin/python`` is deliberately absent: the checked agent can replace it.
ALLOWED_TEST_RUNNER_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("uv", "run", "pytest"),
)
TEST_COMMAND_TIMEOUT_SECONDS = 30


def parse_allowlisted_test_command(cmd: Any, project_root: Any) -> List[str]:
    """Return the argv for an allowlisted test-runner command, else raise ValueError.

    The command is split with ``shlex`` and never passed to a shell.  The reason in the
    ValueError is safe to record; the command itself is not executed.
    """
    argv = split_command(cmd)
    prefix = next(
        (p for p in ALLOWED_TEST_RUNNER_PREFIXES if tuple(argv[: len(p)]) == p),
        None,
    )
    if prefix is None:
        raise ValueError(f"test_runner_not_allowlisted: {argv[0]}")
    check_pytest_args(argv[len(prefix) :], Path(project_root))
    return argv


class EvidenceVerifier:
    """
    在 Audit (A) 階段被呼叫，獨立驗證 Agent 宣稱的 evidence。
    
    Stage 2: Physical Replay Chain.
    """
    
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.replay_runner = ReplayRunner(self.project_root)
        self.anti_drift = AntiDrift(self.project_root, self.project_root / "nexus/config/governance_manifest.json")
    
    def verify(self, evidence_bundle: dict, allow_no_replay: bool = False) -> dict:
        """Verify an evidence bundle.

        Without at least one really replayed (allowlisted) command, the bundle is returned as
        UNCOVERED (reason ``no_replayable_commands``, ``advisory: True``; trust UNKNOWN, or LOW
        when code artifacts are missing or the git diff is empty): replay
        status SKIPPED or NOT_REPLAYED is not verification, but missing coverage is not a
        rejection either (#2624). ``allow_no_replay=True`` is the explicit waiver; the result is
        then labelled ``replay_waived`` and trust is capped at MEDIUM.

        A project without ``nexus/config/governance_manifest.json`` is reported as
        NOT_CONFIGURED (reason ``governance_manifest_not_configured``), not as drift.
        """
        reject_reasons = []
        try:
            # T1: Schema 契約化驗證
            if not self._validate_schema(evidence_bundle, reject_reasons):
                return {
                    "overall_trust": "LOW",
                    "status": "REJECTED",
                    "reason": "schema_mismatch",
                    "reject_reasons": reject_reasons,
                    "code_artifacts_verified": {"all_exist": False},
                    "test_commands_verified": {"all_executed": False},
                }

            # Stage 3: Anti-Drift Check
            drift_passed, drift_results = self.anti_drift.verify_drift()
            if not drift_passed and drift_results.get("error") == "manifest_not_found":
                # No manifest means the anti-drift seal was never set up for this project
                # (e.g. a sibling repo); that is not evidence of drift (#2624).
                return {
                    "overall_trust": "LOW",
                    "status": "NOT_CONFIGURED",
                    "reason": "governance_manifest_not_configured",
                    "drift_results": drift_results,
                    "code_artifacts_verified": {"all_exist": False},
                    "test_commands_verified": {"all_executed": False},
                }
            if not drift_passed:
                return {
                    "overall_trust": "LOW",
                    "status": "REJECTED",
                    "reason": "governance_drift_detected",
                    "drift_results": drift_results,
                }

            # Stage 2: Physical Replay
            replay_report = self.replay_runner.run_replay(evidence_bundle)
            if not replay_report["passed"]:
                return {
                    "overall_trust": "LOW",
                    "status": "REJECTED",
                    "reason": "replay_failed",
                    "replay_report": replay_report,
                }

            replay_executed = int(replay_report.get("replay_count", 0) or 0) > 0
            if not replay_executed and not allow_no_replay:
                # Advisory: nothing was replayed, so nothing is verified, but the absence of a
                # replayable command is a coverage gap, not a rejection (#2624). Code artifacts
                # and the git diff are still checked (no command is executed): missing
                # artifacts or an empty diff keep trust LOW.
                code_artifacts = self._verify_code_artifacts(evidence_bundle.get("code_artifacts", []))
                diff_ok = self._check_git_diff_non_empty()
                if not code_artifacts["all_exist"]:
                    reject_reasons.append("code_artifacts_missing_or_invalid")
                if not diff_ok:
                    reject_reasons.append("empty_git_diff")
                return {
                    "overall_trust": "UNKNOWN" if not reject_reasons else "LOW",
                    "status": "UNCOVERED",
                    "advisory": True,
                    "reason": "no_replayable_commands",
                    "replay_verified": False,
                    "replay_waived": False,
                    "replay_report": replay_report,
                    "reject_reasons": reject_reasons,
                    "code_artifacts_verified": code_artifacts,
                    "git_diff_non_empty": diff_ok,
                    "test_commands_verified": {"all_executed": False},
                }

            results = {
                "replay_verified": replay_executed,
                "replay_waived": not replay_executed,
                "code_artifacts_verified": self._verify_code_artifacts(
                    evidence_bundle.get("code_artifacts", [])
                ),
                "git_diff_non_empty": self._check_git_diff_non_empty(),
                "git_diff_stat": self._get_git_diff_stat(),
                "test_commands_verified": self._verify_test_commands(
                    evidence_bundle.get("test_artifacts", [])
                ),
                "replay_chain": replay_report,
                "overall_trust": "UNKNOWN",
                "reject_reasons": reject_reasons,
            }
            
            # 計算 overall trust
            code_ok = results["code_artifacts_verified"]["all_exist"]
            diff_ok = results["git_diff_non_empty"]
            test_ok = results["test_commands_verified"]["all_executed"]
            
            if not code_ok:
                reject_reasons.append("code_artifacts_missing_or_invalid")
            if not diff_ok:
                reject_reasons.append("empty_git_diff")
            if not test_ok:
                tests_report = results["test_commands_verified"]
                if tests_report.get("uncovered") and not tests_report.get("not_executed"):
                    # Non-allowlisted commands were not run: a coverage gap, not fraud, and
                    # never HIGH trust (#2634).
                    reject_reasons.append("test_commands_uncovered")
                else:
                    reject_reasons.append("test_execution_fraud_detected")

            if code_ok and diff_ok and test_ok:
                results["overall_trust"] = "HIGH"
            elif code_ok and (diff_ok or test_ok):
                results["overall_trust"] = "MEDIUM"
            else:
                results["overall_trust"] = "LOW"
            
            if results["replay_waived"] and results["overall_trust"] == "HIGH":
                results["overall_trust"] = "MEDIUM"

            return results
        except Exception as e:
            # T2: 強制 Fail-Closed
            return {
                "overall_trust": "LOW",
                "reject_reasons": [f"verifier_internal_error: {str(e)}"],
                "code_artifacts_verified": {"all_exist": False},
                "test_commands_verified": {"all_executed": False},
            }

    def _validate_schema(self, bundle: dict, reasons: list) -> bool:
        if not bundle or not isinstance(bundle, dict):
            reasons.append("invalid_bundle_type")
            return False
        if "version" not in bundle:
            reasons.append("missing_schema_version")
            # For backward compatibility during migration, we might warning or fail.
            # Stage 2 requires version.
            return False
        if bundle["version"] != "1.1.0":
            reasons.append(f"unsupported_schema_version: {bundle.get('version')}")
            return False
        if "code_artifacts" not in bundle:
            reasons.append("missing_code_artifacts_key")
            return False
        return True
    
    def _verify_code_artifacts(self, artifacts: list) -> dict:
        missing = []
        untracked = []
        invalid_items = []
        normalized_paths = []
        tracked_files = self._get_tracked_files()
        
        for artifact in artifacts:
            file_path = ""
            if isinstance(artifact, str):
                file_path = artifact
            elif isinstance(artifact, dict):
                file_path = artifact.get("file_path", "")
            
            if not file_path:
                invalid_items.append(artifact)
                continue
            
            normalized_paths.append(file_path)
            path = self.project_root / file_path
            if not path.exists():
                missing.append(file_path)
            elif str(file_path) not in tracked_files:
                untracked.append(file_path)
        
        return {
            "all_exist": len(missing) == 0 and len(invalid_items) == 0,
            "missing": missing,
            "untracked": untracked,
            "invalid_items": invalid_items,
            "normalized_paths": normalized_paths,
            "total": len(artifacts),
        }
    
    def _check_git_diff_non_empty(self) -> bool:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=self.project_root, capture_output=True, text=True
        )
        return bool(result.stdout.strip())
    
    def _get_git_diff_stat(self) -> str:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=self.project_root, capture_output=True, text=True
        )
        return result.stdout.strip()[:500]
    
    def _verify_test_commands(self, test_artifacts: list) -> dict:
        executed = []
        not_executed = []
        uncovered = []

        for cmd_info in test_artifacts:
            cmd = cmd_info if isinstance(cmd_info, str) else cmd_info.get("command", "")
            if not cmd:
                continue
            try:
                argv = parse_allowlisted_test_command(cmd, self.project_root)
            except ValueError as e:
                # Not an allowlisted test runner: advisory coverage gap, never executed (#2634).
                uncovered.append({
                    "command": cmd if isinstance(cmd, str) else repr(cmd),
                    "status": "UNCOVERED",
                    "advisory": True,
                    "executed": False,
                    "reason": str(e),
                })
                continue
            try:
                result = subprocess.run(
                    argv, cwd=self.project_root, stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=TEST_COMMAND_TIMEOUT_SECONDS,
                )
                executed.append({
                    "command": cmd,
                    "exit_code": result.returncode,
                    "passed": result.returncode == 0,
                })
            except subprocess.TimeoutExpired:
                not_executed.append({"command": cmd, "reason": "timeout"})
            except Exception as e:
                not_executed.append({"command": cmd, "reason": str(e)})

        report = {
            # Any UNCOVERED command means not everything claimed was replayed (#2634).
            "all_executed": len(not_executed) == 0 and len(executed) > 0 and not uncovered,
            "executed": executed,
            "not_executed": not_executed,
            "uncovered": uncovered,
        }
        if not executed and not not_executed and uncovered:
            report["status"] = "UNCOVERED"
            report["advisory"] = True
        return report

    def _get_tracked_files(self) -> set:
        result = subprocess.run(
            ["git", "ls-files"], cwd=self.project_root,
            capture_output=True, text=True
        )
        return set(result.stdout.strip().split("\n"))
