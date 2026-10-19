"""
Evidence Verifier: 系統級獨立驗證器。
不依賴 Agent 自述，透過物理命令獨立產生/驗證 evidence。
"""

import io
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    ("uv", "run", "python", "-m", "pytest"),
    ("uv", "run", "python3", "-m", "pytest"),
)
TEST_COMMAND_TIMEOUT_SECONDS = 30
# Base-vs-candidate test-set comparison (#2685): bounded collection, argv only, no shell.
TEST_SET_COLLECT_TIMEOUT_SECONDS = 60
TEST_SET_MAX_REPORTED_IDS = 50
# pytest options that do not run tests: a claim made only of these is not a test-pass claim.
_NON_RUNNING_PYTEST_FLAGS = frozenset({"--version", "--co", "--collect-only"})
# pytest options whose value is the next argv item (from the shared allowlist).
_PYTEST_VALUE_OPTIONS = frozenset(
    {"-k", "-m", "-r", "-p", "--tb", "--maxfail", "--durations", "--capture", "--color", "--deselect"}
)


def _allowlisted_prefix(argv: List[str]) -> Optional[Tuple[str, ...]]:
    return next(
        (p for p in ALLOWED_TEST_RUNNER_PREFIXES if tuple(argv[: len(p)]) == p),
        None,
    )


def _pytest_targets(args: List[str]) -> Optional[List[str]]:
    """Positional test targets of an (already allowlisted) pytest argv tail.

    Returns None when the command does not run tests (``--version``, ``--collect-only``).
    """
    targets: List[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg in _NON_RUNNING_PYTEST_FLAGS:
            return None
        if not arg.startswith("-"):
            targets.append(arg)
            continue
        if arg in _PYTEST_VALUE_OPTIONS:
            index += 1  # the value is the next item
    return targets


def _parse_collected_ids(stdout: str) -> List[str]:
    return sorted({
        line.strip() for line in stdout.splitlines() if "::" in line and not line.startswith(" ")
    })


def collect_test_ids(
    prefix: Tuple[str, ...], targets: List[str], cwd: Path
) -> Tuple[Optional[List[str]], str]:
    """Collect pytest node ids under ``cwd`` (argv only, no shell, bounded timeout).

    Returns (ids, "") or (None, reason) when collection is impossible.  Exit 5 (no tests
    collected) is an empty, valid collection.
    """
    argv = [*prefix, "--collect-only", "-q", "-p", "no:cacheprovider", f"--rootdir={cwd}", *targets]
    try:
        result = subprocess.run(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=TEST_SET_COLLECT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, "collect_timeout"
    except Exception as exc:  # e.g. interpreter missing
        return None, f"collect_error: {exc}"
    if result.returncode == 5:
        return [], ""
    if result.returncode != 0:
        return None, f"collect_exit_{result.returncode}"
    return _parse_collected_ids(result.stdout), ""


def parse_allowlisted_test_command(cmd: Any, project_root: Any) -> List[str]:
    """Return the argv for an allowlisted test-runner command, else raise ValueError.

    The command is split with ``shlex`` and never passed to a shell.  The reason in the
    ValueError is safe to record; the command itself is not executed.
    """
    argv = split_command(cmd)
    prefix = _allowlisted_prefix(argv)
    if prefix is None:
        raise ValueError(f"test_runner_not_allowlisted: {argv[0]}")
    check_pytest_args(argv[len(prefix) :], Path(project_root))
    return argv


class EvidenceVerifier:
    """
    在 Audit (A) 階段被呼叫，獨立驗證 Agent 宣稱的 evidence。
    
    Stage 2: Physical Replay Chain.
    """
    
    def __init__(self, project_root: Path, base_ref: str = "HEAD"):
        self.project_root = Path(project_root)
        # The base the candidate (working tree) is compared against: the same ref the
        # git-diff check uses.
        self.base_ref = base_ref
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
            # SKIPPED / NOT_REPLAYED: nothing was replayed.  passed is False since #2685, but
            # that is a coverage gap (UNVERIFIED), not a failed replay (#2624).
            nothing_replayed = replay_report.get("status") in {"SKIPPED", "NOT_REPLAYED"}
            if not replay_report["passed"] and not nothing_replayed:
                return {
                    "overall_trust": "LOW",
                    "status": "REJECTED",
                    "reason": "replay_failed",
                    "replay_report": replay_report,
                }

            replay_executed = (
                not nothing_replayed and int(replay_report.get("replay_count", 0) or 0) > 0
            )
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
                    "verdict": "UNVERIFIED",
                    "passed": False,
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
                if any(not item["passed"] for item in tests_report.get("executed", [])):
                    # A test command really failed now: not a pass, whatever was recorded (#2685).
                    reject_reasons.append("test_commands_failed")
                elif tests_report.get("uncovered") and not tests_report.get("not_executed"):
                    # Non-allowlisted commands were not run: a coverage gap, not fraud, and
                    # never HIGH trust (#2634).
                    reject_reasons.append("test_commands_uncovered")
                else:
                    reject_reasons.append("test_execution_fraud_detected")

            # A declared non-zero exit may pass, but it never counts toward HIGH (#2685).
            tests_report = results["test_commands_verified"]
            if test_ok and not tests_report.get("all_exit_zero", False):
                reject_reasons.append("declared_nonzero_exit")

            # Base-vs-candidate test-set comparison (#2685): the claim says the tests pass,
            # so base test ids that vanished on the candidate are a finding.
            test_set: Dict[str, Any] = {"status": "NOT_APPLICABLE"}
            if test_ok:
                test_set = self._compare_test_sets(tests_report.get("executed", []))
            results["test_set_comparison"] = test_set
            if test_set["status"] == "TESTS_REMOVED":
                reject_reasons.append("tests_removed")
            elif test_set["status"] == "UNKNOWN":
                reject_reasons.append("test_set_comparison_unknown")
            high_blocked = (
                "declared_nonzero_exit" in reject_reasons
                or test_set["status"] in {"TESTS_REMOVED", "UNKNOWN"}
            )

            if code_ok and diff_ok and test_ok:
                results["overall_trust"] = "HIGH"
            elif code_ok and (diff_ok or test_ok):
                results["overall_trust"] = "MEDIUM"
            else:
                results["overall_trust"] = "LOW"
            
            if (results["replay_waived"] or high_blocked) and results["overall_trust"] == "HIGH":
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
    
    def _base_tree(self, dest: Path) -> Optional[str]:
        """Materialize ``base_ref`` into ``dest`` without touching the repository.

        Uses ``git archive`` (no worktree, index or ref changes).  Returns an error
        reason, or None on success.
        """
        try:
            archive = subprocess.run(
                ["git", "archive", "--format=tar", self.base_ref],
                cwd=self.project_root, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=TEST_SET_COLLECT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return "base_archive_timeout"
        except Exception as exc:
            return f"base_archive_error: {exc}"
        if archive.returncode != 0:
            return f"base_archive_exit_{archive.returncode}"
        if not hasattr(tarfile, "data_filter"):
            return "base_extract_unsupported: tarfile data filter unavailable"
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                tar.extractall(dest, filter="data")
        except Exception as exc:
            return f"base_extract_error: {exc}"
        return None

    def _compare_test_sets(self, executed: list) -> Dict[str, Any]:
        """Compare test ids collected on base and candidate for the claimed test targets.

        TESTS_REMOVED when a base id is missing on the candidate; UNKNOWN when either
        side cannot be collected (never grounds for HIGH); OK otherwise.
        """
        runs: List[Tuple[Tuple[str, ...], List[str]]] = []
        for item in executed:
            if not item.get("passed"):
                continue
            try:
                argv = parse_allowlisted_test_command(item.get("command"), self.project_root)
            except ValueError:
                continue
            prefix = _allowlisted_prefix(argv)
            if prefix is None:
                continue
            targets = _pytest_targets(argv[len(prefix):])
            if targets is not None:
                runs.append((prefix, targets))
        if not runs:
            return {"status": "NOT_APPLICABLE", "reason": "no_test_running_command"}

        base_ids: set = set()
        candidate_ids: set = set()
        with tempfile.TemporaryDirectory(prefix="nexus_base_tests_") as tmp:
            # Resolve both roots (/var -> /private/var): pytest node ids are relative to
            # --rootdir, and an unresolved root yields ids that never match.
            base_root = Path(tmp).resolve()
            candidate_root = self.project_root.resolve()
            error = self._base_tree(base_root)
            if error:
                return {"status": "UNKNOWN", "reason": error}
            for prefix, targets in runs:
                cand, reason = collect_test_ids(prefix, targets, candidate_root)
                if cand is None:
                    return {"status": "UNKNOWN", "reason": f"candidate_{reason}"}
                candidate_ids.update(cand)
                # Targets that do not exist on base (new test files) contribute no base ids.
                base_targets = [
                    t for t in targets if (base_root / t.split("::", 1)[0]).exists()
                ]
                if targets and not base_targets:
                    continue
                base, reason = collect_test_ids(prefix, base_targets, base_root)
                if base is None:
                    return {"status": "UNKNOWN", "reason": f"base_{reason}"}
                base_ids.update(base)
        removed = sorted(base_ids - candidate_ids)
        report: Dict[str, Any] = {
            "status": "TESTS_REMOVED" if removed else "OK",
            "base_ref": self.base_ref,
            "base_count": len(base_ids),
            "candidate_count": len(candidate_ids),
            "removed_count": len(removed),
            "removed_ids": removed[:TEST_SET_MAX_REPORTED_IDS],
        }
        if removed:
            report["finding"] = (
                f"{len(removed)} test id(s) collected on {self.base_ref} are missing on the "
                f"candidate while the claim says the tests pass: "
                + ", ".join(removed[:TEST_SET_MAX_REPORTED_IDS])
            )
        return report

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
                # Passed only on a real exit 0, or on an explicitly declared non-zero
                # exit (``expected_exit_code``); a recorded exit code is not a declaration.
                declared = cmd_info.get("expected_exit_code") if isinstance(cmd_info, dict) else None
                declared_ok = (
                    isinstance(declared, int)
                    and not isinstance(declared, bool)
                    and declared != 0
                    and result.returncode == declared
                )
                executed.append({
                    "command": cmd,
                    "exit_code": result.returncode,
                    "exit_zero": result.returncode == 0,
                    "declared_expected_exit_code": declared,
                    "passed": result.returncode == 0 or declared_ok,
                })
            except subprocess.TimeoutExpired:
                not_executed.append({"command": cmd, "reason": "timeout"})
            except Exception as e:
                not_executed.append({"command": cmd, "reason": str(e)})

        report = {
            # Any UNCOVERED command means not everything claimed was replayed (#2634).
            # ... and every executed command must have passed (#2685).
            "all_executed": (
                len(not_executed) == 0
                and len(executed) > 0
                and not uncovered
                and all(item["passed"] for item in executed)
            ),
            "all_exit_zero": bool(executed) and all(item["exit_zero"] for item in executed),
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
