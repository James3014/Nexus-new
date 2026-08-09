import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class TestResult:
    test_id: str
    passed: bool
    output: str
    is_hidden: bool = False


@dataclass(frozen=True)
class AffectedSuiteManifest:
    """The immutable, affected regression suite contract for one repair."""

    test_ids: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        test_ids = tuple(str(test_id) for test_id in self.test_ids)
        commands = tuple(tuple(str(arg) for arg in command) for command in self.commands)
        object.__setattr__(self, "test_ids", test_ids)
        object.__setattr__(self, "commands", commands)

    @property
    def test_count(self) -> int:
        return len(self.test_ids)

    @property
    def canonical_bytes(self) -> bytes:
        payload = {"commands": self.commands, "test_ids": self.test_ids}
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def identity(self) -> str:
        return f"affected-suite-v1:{self.sha256}"


@dataclass(frozen=True)
class RegressionSuiteBinding:
    """Evidence-only result of binding one suite to base and Candidate."""

    eligible: bool
    reason_code: str
    suite_identity: str
    suite_hash: str
    test_count: int
    base_sha: str
    candidate_sha: str
    failure_evidence: tuple[str, ...] = ()


def _binding_rejection(
    manifest: AffectedSuiteManifest,
    reason_code: str,
    *,
    base_sha: str = "",
    candidate_sha: str = "",
    failure_evidence: tuple[str, ...] = (),
) -> RegressionSuiteBinding:
    return RegressionSuiteBinding(
        eligible=False,
        reason_code=reason_code,
        suite_identity=manifest.identity,
        suite_hash=manifest.sha256,
        test_count=manifest.test_count,
        base_sha=base_sha,
        candidate_sha=candidate_sha,
        failure_evidence=failure_evidence,
    )


def _compile_only(command: tuple[str, ...]) -> bool:
    lowered = tuple(argument.lower() for argument in command)
    joined = " ".join(lowered)
    return (
        "--collect-only" in lowered
        or "compileall" in lowered
        or "py_compile" in joined
        or (" compile " in f" {joined} ")
    )


def _result_ids(results: List[TestResult]) -> tuple[str, ...] | None:
    ids = tuple(result.test_id for result in results)
    return ids if len(ids) == len(set(ids)) else None


def _suite_hash_format_valid(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def bind_affected_regression_suite(
    manifest: AffectedSuiteManifest,
    *,
    base_sha: str,
    candidate_sha: str,
    base_results: List[TestResult],
    candidate_results: List[TestResult],
    affected_test_ids: tuple[str, ...] | list[str] | None = None,
    expected_suite_hash: str | None = None,
    base_suite_hash: str | None = None,
    candidate_suite_hash: str | None = None,
) -> RegressionSuiteBinding:
    """Fail closed unless the exact affected suite passes on both workspaces.

    This binds already-produced ``TestResult`` evidence; it does not execute a
    second verifier and is not mounted as the repository-wide evaluation path.
    """
    if not isinstance(manifest, AffectedSuiteManifest):
        raise TypeError("manifest must be an AffectedSuiteManifest")
    if not manifest.test_ids or not manifest.commands:
        return _binding_rejection(
            manifest, "SUITE_EMPTY", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if manifest.test_count != len(manifest.commands):
        return _binding_rejection(
            manifest, "SUITE_TEST_COUNT_MISMATCH", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if any(
        not test_id or not command for test_id, command in zip(manifest.test_ids, manifest.commands)
    ):
        return _binding_rejection(
            manifest, "SUITE_EMPTY", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if all(_compile_only(command) for command in manifest.commands):
        return _binding_rejection(
            manifest, "SUITE_COMPILE_ONLY", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if not base_sha or not candidate_sha or base_sha == candidate_sha:
        return _binding_rejection(
            manifest,
            "BASE_CANDIDATE_BINDING_INVALID",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if base_suite_hash is None and candidate_suite_hash is None:
        return _binding_rejection(
            manifest,
            "SUITE_HASH_BINDINGS_MISSING",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if base_suite_hash is None:
        return _binding_rejection(
            manifest,
            "BASE_SUITE_HASH_MISSING",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if candidate_suite_hash is None:
        return _binding_rejection(
            manifest,
            "CANDIDATE_SUITE_HASH_MISSING",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if base_suite_hash == "":
        return _binding_rejection(
            manifest,
            "BASE_SUITE_HASH_MISSING",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if candidate_suite_hash == "":
        return _binding_rejection(
            manifest,
            "CANDIDATE_SUITE_HASH_MISSING",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if not _suite_hash_format_valid(base_suite_hash):
        return _binding_rejection(
            manifest,
            "BASE_SUITE_HASH_INVALID",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if not _suite_hash_format_valid(candidate_suite_hash):
        return _binding_rejection(
            manifest,
            "CANDIDATE_SUITE_HASH_INVALID",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
        )
    if expected_suite_hash is not None and expected_suite_hash != manifest.sha256:
        return _binding_rejection(
            manifest, "SUITE_HASH_DRIFT", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if base_suite_hash is not None and base_suite_hash != manifest.sha256:
        return _binding_rejection(
            manifest, "BASE_SUITE_HASH_DRIFT", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if candidate_suite_hash is not None and candidate_suite_hash != manifest.sha256:
        return _binding_rejection(
            manifest, "CANDIDATE_SUITE_HASH_DRIFT", base_sha=base_sha, candidate_sha=candidate_sha
        )
    if affected_test_ids is None or set(affected_test_ids) != set(manifest.test_ids):
        return _binding_rejection(
            manifest, "SUITE_UNRELATED_OR_UNBOUND", base_sha=base_sha, candidate_sha=candidate_sha
        )

    expected_ids = set(manifest.test_ids)
    base_ids = _result_ids(base_results)
    candidate_ids = _result_ids(candidate_results)
    if (
        base_ids is None
        or candidate_ids is None
        or set(base_ids) != expected_ids
        or set(candidate_ids) != expected_ids
    ):
        return _binding_rejection(
            manifest, "SUITE_RESULT_MISMATCH", base_sha=base_sha, candidate_sha=candidate_sha
        )

    failures: list[str] = []
    for label, results in (("base", base_results), ("candidate", candidate_results)):
        for result in results:
            if not result.passed:
                evidence = result.output or "<no failure output>"
                failures.append(f"{label}:{result.test_id}: {evidence}")
    if failures:
        return _binding_rejection(
            manifest,
            "SUITE_TEST_FAILED",
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            failure_evidence=tuple(failures),
        )
    return RegressionSuiteBinding(
        eligible=True,
        reason_code="AFFECTED_SUITE_PASS",
        suite_identity=manifest.identity,
        suite_hash=manifest.sha256,
        test_count=manifest.test_count,
        base_sha=base_sha,
        candidate_sha=candidate_sha,
    )


RegressionSuiteManifest = AffectedSuiteManifest
bind_regression_suite = bind_affected_regression_suite


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
            test_timeout = int(os.environ.get("NEXUS_TEST_TIMEOUT_SECONDS", "300"))
            try:
                res = subprocess.run(
                    cmd,
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=test_timeout,
                    env=env,
                )
                results.append(
                    TestResult(
                        test_id=" ".join(cmd),
                        passed=(res.returncode == 0),
                        output=res.stdout + res.stderr,
                    )
                )
            except Exception as e:
                results.append(TestResult(test_id=" ".join(cmd), passed=False, output=str(e)))
        return results

    def run_hidden_verifier(self, cmds: List[List[str]]) -> List[TestResult]:
        if not cmds:
            return [
                TestResult(
                    test_id="hidden_verifier_configured",
                    passed=False,
                    output="Hidden verifier required but no verifier command was configured.",
                    is_hidden=True,
                )
            ]
        results = []
        for cmd in cmds:
            env = os.environ.copy()
            benchmarks_dir = str(self.repo_dir / "scripts/benchmarks")
            env["PYTHONPATH"] = f"{str(self.repo_dir)}:{benchmarks_dir}:{env.get('PYTHONPATH', '')}"
            test_timeout = int(os.environ.get("NEXUS_TEST_TIMEOUT_SECONDS", "300"))
            try:
                res = subprocess.run(
                    cmd,
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=test_timeout,
                    env=env,
                )
                results.append(
                    TestResult(
                        test_id=" ".join(cmd),
                        passed=(res.returncode == 0),
                        output=res.stdout + res.stderr,
                        is_hidden=True,
                    )
                )
            except Exception as e:
                results.append(
                    TestResult(test_id=" ".join(cmd), passed=False, output=str(e), is_hidden=True)
                )
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
