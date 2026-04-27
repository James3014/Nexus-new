from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FLEET_LANES = ("security_sentry", "logic_breaker", "ghost_regression")
SCHEMA_VERSION = "ultra-review.v1"
GHOST_REGRESSION_TIMEOUT_SEC = 30
LOGIC_BREAKER_TIMEOUT_SEC = 15
TEST_DIR_BY_SOURCE_DIR = {
    "app": "tests/app",
    "core": "tests/core",
    "delivery": "tests/delivery",
    "engine": "tests/engine",
    "health": "tests/health",
    "orchestrator": "tests/orchestrator",
    "research": "tests/research",
    "services": "tests/services",
}
SECURITY_PATTERNS = (
    ("secret_literal", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{8,}['\"]")),
    ("shell_true_subprocess", re.compile(r"subprocess\.(run|Popen|call|check_output)\([^#\n]*shell\s*=\s*True")),
    ("unsafe_delete", re.compile(r"shutil\.rmtree\([^#\n]*(ignore_errors\s*=\s*True|force|/tmp|\*)")),
)
SECURITY_REPRO_TIMEOUT_SEC = 10


class UltraReviewError(RuntimeError):
    """Raised when ultra-review cannot produce a trustworthy report."""


class UltraReviewService:
    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root).resolve()

    def run(
        self,
        *,
        dry_run: bool = True,
        task: str = "",
        base_ref: str = "HEAD",
        report_path: Path | str = ".nexus/reports/ultra_review_report.json",
        sandbox_root: Path | str = ".nexus/reports/ultra_review/sandboxes",
    ) -> dict[str, Any]:
        if not dry_run:
            raise UltraReviewError("ultra-review currently supports --dry-run only")

        run_id = self._run_id()
        sandbox_path = self._prepare_sandbox(Path(sandbox_root), run_id)
        progress_path = sandbox_path / "progress.jsonl"
        progress: list[dict[str, Any]] = []
        self._record_progress(progress, progress_path, "sandbox_prepared", sandbox_path=str(sandbox_path))
        diff_text = self._capture_diff(base_ref)
        status_text = self._git(["status", "--short"])

        diff_path = sandbox_path / "changes.diff"
        diff_path.write_text(diff_text, encoding="utf-8")
        (sandbox_path / "git_status.txt").write_text(status_text, encoding="utf-8")
        changed_files = self._changed_files(diff_text)
        self._record_progress(
            progress,
            progress_path,
            "diff_captured",
            changed_files=len(changed_files),
            bytes=len(diff_text.encode("utf-8")),
        )

        regression_map = self._derive_regression_candidate_map(diff_text)
        test_candidates = self._existing_regression_candidates(regression_map)
        execution_root, mirror_metadata = self._prepare_execution_workspace(sandbox_path, diff_path=diff_path)
        security_sentry = self._run_security_sentry(
            diff_text=diff_text,
            execution_root=execution_root,
            sandbox_path=sandbox_path,
        )
        self._record_progress(
            progress,
            progress_path,
            "security_sentry_complete",
            passed=security_sentry["passed"],
            verified_findings=security_sentry["verified_findings"],
            unverified_observations=security_sentry["unverified_observations"],
        )
        logic_breaker = self._run_logic_breaker(
            diff_path=diff_path,
            execution_root=execution_root,
            sandbox_path=sandbox_path,
        )
        self._record_progress(progress, progress_path, "logic_breaker_complete", passed=logic_breaker["passed"])
        ghost_regression = self._run_ghost_regression(test_candidates, execution_root=execution_root)
        self._record_progress(progress, progress_path, "ghost_regression_complete", passed=ghost_regression["passed"])
        findings = [*security_sentry["findings"], *logic_breaker["findings"], *ghost_regression["findings"]]
        gate_passed = bool(security_sentry["passed"] and logic_breaker["passed"] and ghost_regression["passed"])
        fleet = self._build_dry_run_fleet(test_candidates, security_sentry, logic_breaker, ghost_regression)
        out_path = self._resolve(report_path)
        self._record_progress(progress, progress_path, "report_written", report_path=str(out_path))
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": "DRY_RUN_PASS" if gate_passed else "DRY_RUN_FAIL",
            "gate_passed": gate_passed,
            "mode": "dry-run",
            "task": task,
            "base_ref": base_ref,
            "project_root": str(self.project_root),
            "sandbox_path": str(sandbox_path),
            "sandbox_mirror": mirror_metadata,
            "artifacts": {
                "diff": str(diff_path),
                "git_status": str(sandbox_path / "git_status.txt"),
                "progress_log": str(progress_path),
            },
            "diff": {
                "bytes": len(diff_text.encode("utf-8")),
                "changed_files": changed_files,
                "has_worktree_delta": bool(diff_text.strip() or status_text.strip()),
            },
            "fleet": fleet,
            "findings": findings,
            "security_sentry": {k: v for k, v in security_sentry.items() if k != "findings"},
            "logic_breaker": {k: v for k, v in logic_breaker.items() if k != "findings"},
            "ghost_regression": {k: v for k, v in ghost_regression.items() if k != "findings"},
            "summary": {
                "security_verified_findings": security_sentry["verified_findings"],
                "security_unverified_observations": security_sentry["unverified_observations"],
                "logic_breaker_passed": logic_breaker["passed"],
                "ghost_regression_passed": ghost_regression["passed"],
                "executed_regression_tests": len(ghost_regression["executed_tests"]),
                "verified_findings": sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING"),
            },
            "progress": progress,
            "regression_candidate_map": regression_map,
            "verification": {
                "verified_findings": sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING"),
                "unverified_observations": sum(1 for finding in findings if finding.get("state") != "VERIFIED_FINDING"),
                "reproduction_required": True,
                "negative_test_execution": "executed" if test_candidates else "not_applicable_no_candidates",
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "report_path": str(out_path),
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    def _record_progress(self, progress: list[dict[str, Any]], progress_path: Path, stage: str, **fields: Any) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            **fields,
        }
        progress.append(event)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _prepare_sandbox(self, sandbox_root: Path, run_id: str) -> Path:
        root = self._resolve(sandbox_root)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_path = root / run_id
        sandbox_path.mkdir(parents=False, exist_ok=False)
        (sandbox_path / "README.txt").write_text(
            "Nexus ultra-review dry-run sandbox. Contains captured diff artifacts only.\n",
            encoding="utf-8",
        )
        return sandbox_path

    def _prepare_execution_workspace(self, sandbox_path: Path, *, diff_path: Path) -> tuple[Path, dict[str, Any]]:
        execution_root = sandbox_path / "worktree"
        metadata = self._prepare_git_worktree_mirror(execution_root, diff_path=diff_path, sandbox_path=sandbox_path)
        if metadata.get("strategy") == "git_worktree":
            return execution_root, metadata

        fallback_metadata = self._copy_execution_workspace(execution_root, sandbox_path)
        fallback_metadata["fallback_reason"] = metadata.get("fallback_reason", "")
        return execution_root, fallback_metadata

    def _prepare_git_worktree_mirror(self, execution_root: Path, *, diff_path: Path, sandbox_path: Path) -> dict[str, Any]:
        add_cmd = ["git", "worktree", "add", "--detach", str(execution_root), "HEAD"]
        add = subprocess.run(add_cmd, cwd=self.project_root, capture_output=True, text=True, check=False)
        if add.returncode != 0:
            return {
                "strategy": "copytree",
                "fallback_reason": (add.stderr or add.stdout or "git worktree add failed")[-1000:],
            }

        diff_has_content = bool(diff_path.read_text(encoding="utf-8").strip()) if diff_path.exists() else False
        if not diff_has_content:
            untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
            return {
                "strategy": "git_worktree",
                "diff_applied": True,
                "command": " ".join(add_cmd),
                "untracked_overlay_count": untracked_overlay_count,
                "empty_diff": True,
            }

        apply_cmd = ["git", "apply", "--index", "--binary", str(diff_path)]
        apply = subprocess.run(apply_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
        if apply.returncode != 0:
            apply_cmd = ["git", "apply", "--binary", str(diff_path)]
            apply = subprocess.run(apply_cmd, cwd=execution_root, capture_output=True, text=True, check=False)
        if apply.returncode != 0:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(execution_root)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            return {
                "strategy": "copytree",
                "diff_applied": False,
                "fallback_reason": (apply.stderr or apply.stdout or "git apply failed")[-1000:],
                "command": " ".join(add_cmd),
            }

        untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
        return {
            "strategy": "git_worktree",
            "diff_applied": True,
            "command": " ".join(add_cmd),
            "untracked_overlay_count": untracked_overlay_count,
        }

    def _overlay_untracked_files(self, execution_root: Path, *, sandbox_path: Path) -> int:
        ls = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=self.project_root,
            capture_output=True,
            text=False,
            check=False,
        )
        if ls.returncode != 0:
            return 0
        count = 0
        for raw in ls.stdout.split(b"\0"):
            if not raw:
                continue
            rel = raw.decode("utf-8", errors="ignore")
            source = self.project_root / rel
            target = execution_root / rel
            try:
                if source.resolve().is_relative_to(sandbox_path.resolve()):
                    continue
            except OSError:
                continue
            if not source.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            count += 1
        return count

    def _copy_execution_workspace(self, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        ignored_patterns = shutil.ignore_patterns(
            ".git",
            ".venv",
            ".nexus",
            ".pytest_cache",
            "__pycache__",
            "MagicMock",
            "compliance/audit",
        )

        def ignore(path: str, names: list[str]) -> set[str]:
            ignored = set(ignored_patterns(path, names))
            current = Path(path).resolve()
            if current == self.project_root:
                try:
                    sandbox_anchor = sandbox_path.relative_to(self.project_root).parts[0]
                except ValueError:
                    sandbox_anchor = ""
                if sandbox_anchor in names:
                    ignored.add(sandbox_anchor)
            return ignored

        shutil.copytree(self.project_root, execution_root, ignore=ignore)
        return {"strategy": "copytree", "diff_applied": True}

    def _capture_diff(self, base_ref: str) -> str:
        return self._git(["diff", "--binary", base_ref])

    def _derive_regression_candidate_map(self, diff_text: str) -> list[dict[str, Any]]:
        candidate_map: list[dict[str, Any]] = []
        for changed in self._changed_files(diff_text):
            path = Path(changed)
            if not path.parts:
                continue
            candidates = self._candidate_tests_for_changed_file(path)
            existing = [candidate for candidate in candidates if (self.project_root / candidate).exists()]
            candidate_map.append(
                {
                    "changed_file": changed,
                    "candidates": candidates,
                    "existing": existing,
                    "skipped": [candidate for candidate in candidates if candidate not in existing],
                    "status": "READY" if existing else "SKIPPED",
                    "skip_reason": "" if existing else "no_existing_regression_candidates",
                }
            )
        return candidate_map

    def _candidate_tests_for_changed_file(self, path: Path) -> list[str]:
        candidates: list[str] = []
        if path.parts[0] == "nexus" and path.suffix == ".py":
            stem = path.stem
            module_dir = path.parts[1] if len(path.parts) > 1 else ""
            test_dir = TEST_DIR_BY_SOURCE_DIR.get(module_dir, f"tests/{module_dir}" if module_dir else "tests")
            candidates.extend(
                [
                    f"{test_dir}/test_{stem}.py",
                    f"tests/test_{stem}.py",
                ]
            )
        if path.parts[0] == "scripts" and path.suffix == ".py":
            script_area = path.parts[1] if len(path.parts) > 1 else ""
            test_dir = "tests/ops" if script_area == "ops" else "tests/engine"
            candidates.append(f"{test_dir}/test_{path.stem}.py")

        seen: set[str] = set()
        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped

    def _existing_regression_candidates(self, regression_map: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        existing: list[str] = []
        for item in regression_map:
            for candidate in item.get("existing", []):
                if candidate in seen:
                    continue
                seen.add(candidate)
                existing.append(candidate)
        return existing

    def _scan_security_observations(self, diff_text: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        current_file = ""
        new_line = 0
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("diff --git "):
                current_file = self._path_from_diff_header(raw_line)
                new_line = 0
                continue
            if raw_line.startswith("@@"):
                parsed = re.search(r"\+(\d+)", raw_line)
                new_line = int(parsed.group(1)) - 1 if parsed else 0
                continue
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                new_line += 1
                content = raw_line[1:]
                for rule_id, pattern in SECURITY_PATTERNS:
                    if pattern.search(content):
                        findings.append(
                            {
                                "id": f"security-{len(findings) + 1}",
                                "lane": "security_sentry",
                                "rule_id": rule_id,
                                "state": "UNVERIFIED_OBSERVATION",
                                "severity": "high" if rule_id == "secret_literal" else "medium",
                                "file": current_file,
                                "line": new_line,
                                "repro_command": "",
                                "matched_text": content,
                                "summary": f"Dry-run security observation matched {rule_id}.",
                            }
                        )
                continue
            if raw_line.startswith("-") and not raw_line.startswith("---"):
                continue
            if current_file:
                new_line += 1
        return findings

    def _path_from_diff_header(self, line: str) -> str:
        parsed = re.match(r"^diff --git a/(.*) b/(.*)$", line)
        if parsed:
            return parsed.group(2)
        parts = line.split()
        if len(parts) < 4:
            return ""
        path = parts[3]
        return path[2:] if path.startswith("b/") else path

    def _derive_regression_candidates(self, diff_text: str) -> list[str]:
        return self._existing_regression_candidates(self._derive_regression_candidate_map(diff_text))

    def _build_dry_run_fleet(
        self,
        test_candidates: list[str],
        security_sentry: dict[str, Any] | None = None,
        logic_breaker: dict[str, Any] | None = None,
        ghost_regression: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        security_sentry = security_sentry or {
            "passed": True,
            "findings": [],
            "verified_findings": 0,
            "unverified_observations": 0,
        }
        logic_breaker = logic_breaker or {
            "passed": True,
            "repro_script": "",
            "repro_command": "",
        }
        ghost_regression = ghost_regression or {
            "passed": True,
            "executed_tests": [],
            "failed_tests": [],
            "skipped_tests": [],
        }
        ghost_status = "SKIPPED"
        if test_candidates:
            ghost_status = "PASS" if bool(ghost_regression.get("passed", False)) else "FAIL"
        logic_status = "PASS" if bool(logic_breaker.get("passed", False)) else "FAIL"
        return [
            {
                "lane": "security_sentry",
                "status": "PASS" if security_sentry.get("passed", True) else "FAIL",
                "planned_checks": ["secret-pattern-scan", "dangerous-subprocess-scan"],
                "executed_checks": security_sentry.get("executed_checks", []),
                "unverified_observations": security_sentry.get("unverified_observations", 0),
                "verified_findings": security_sentry.get("verified_findings", 0),
            },
            {
                "lane": "logic_breaker",
                "status": logic_status,
                "planned_checks": ["edge-case-review-card-generation"],
                "executed_checks": ["ultra_logic_repro.py"],
                "repro_script": logic_breaker.get("repro_script", ""),
                "verified_findings": 0 if logic_breaker.get("passed", True) else 1,
            },
            {
                "lane": "ghost_regression",
                "status": ghost_status,
                "planned_checks": test_candidates,
                "executed_checks": ghost_regression.get("executed_tests", []),
                "failed_checks": ghost_regression.get("failed_tests", []),
                "skipped_checks": ghost_regression.get("skipped_tests", []),
                "skip_reason": "" if test_candidates else "no_existing_regression_candidates",
                "verified_findings": len(ghost_regression.get("failed_tests", [])),
            },
        ]

    def _run_security_sentry(self, *, diff_text: str, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        observations = self._scan_security_observations(diff_text)
        findings: list[dict[str, Any]] = []
        executed_checks: list[str] = []
        verified_count = 0
        unverified_count = 0

        for index, observation in enumerate(observations, start=1):
            script_name = f"ultra_security_repro_{index}.py"
            script_path = sandbox_path / script_name
            expected = str(observation.get("matched_text", ""))
            script_path.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "",
                        f"expected = {expected!r}",
                        "diff_text = Path('changes.diff').read_text(encoding='utf-8')",
                        "if expected not in diff_text:",
                        "    raise SystemExit('security observation not reproduced')",
                        "print('security_repro_ok')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            shutil.copy2(self._resolve(sandbox_path / "changes.diff"), execution_root / "changes.diff")
            cmd = ["uv", "run", "--active", "python", str(script_path)]
            executed_checks.append(script_name)
            timeout = False
            try:
                result = subprocess.run(
                    cmd,
                    cwd=execution_root,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=SECURITY_REPRO_TIMEOUT_SEC,
                )
                reproduced = result.returncode == 0
                stdout_tail = (result.stdout or "")[-2000:]
                stderr_tail = (result.stderr or "")[-2000:]
            except subprocess.TimeoutExpired as exc:
                reproduced = False
                timeout = True
                stdout_tail = str(exc.output or "")[-2000:]
                stderr_tail = str(exc.stderr or "")[-2000:]
            finding = dict(observation)
            finding.update(
                {
                    "repro_command": " ".join(cmd),
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                    "timeout_sec": SECURITY_REPRO_TIMEOUT_SEC,
                    "timeout": timeout,
                }
            )
            if reproduced:
                finding["state"] = "VERIFIED_FINDING"
                finding["summary"] = f"Security Sentry reproduced {finding['rule_id']} from diff evidence."
                verified_count += 1
            else:
                finding["state"] = "UNVERIFIED_OBSERVATION"
                finding["summary"] = f"Security Sentry observed {finding['rule_id']} but repro did not confirm it."
                unverified_count += 1
            findings.append(finding)

        return {
            "passed": verified_count == 0,
            "executed_checks": executed_checks,
            "verified_findings": verified_count,
            "unverified_observations": unverified_count,
            "timeout_sec": SECURITY_REPRO_TIMEOUT_SEC,
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "dependency_mode": "active_venv",
            "findings": findings,
        }

    def _run_logic_breaker(self, *, diff_path: Path, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        repro_script = sandbox_path / "ultra_logic_repro.py"
        mirror_diff_path = execution_root / ".nexus_ultra_changes.diff"
        shutil.copy2(diff_path, mirror_diff_path)
        repro_script.write_text(
            "\n".join(
                [
                    "import re",
                    "from pathlib import Path",
                    "",
                    "diff_path = Path('.nexus_ultra_changes.diff')",
                    "if not diff_path.exists():",
                    "    raise SystemExit('missing diff artifact')",
                    "diff_text = diff_path.read_text(encoding='utf-8')",
                    "for line in diff_text.splitlines():",
                    "    if not line.startswith('diff --git '):",
                    "        continue",
                    "    parsed = re.match(r'^diff --git a/(.*) b/(.*)$', line)",
                    "    if not parsed:",
                    "        raise SystemExit(f'malformed diff header: {line}')",
                    "    changed = parsed.group(2)",
                    "    if changed and not Path(changed).exists():",
                    "        raise SystemExit(f'changed file missing from sandbox mirror: {changed}')",
                    "print('logic_repro_ok')",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        cmd = ["uv", "run", "--active", "python", str(repro_script)]
        timeout = False
        try:
            result = subprocess.run(
                cmd,
                cwd=execution_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=LOGIC_BREAKER_TIMEOUT_SEC,
            )
            passed = result.returncode == 0
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            rule_id = "logic_repro_failed"
            summary = "Logic Breaker deterministic repro failed in ultra-review dry-run."
        except subprocess.TimeoutExpired as exc:
            passed = False
            timeout = True
            stdout_tail = str(exc.output or "")[-2000:]
            stderr_tail = str(exc.stderr or "")[-2000:]
            rule_id = "logic_repro_timeout"
            summary = "Logic Breaker deterministic repro timed out in ultra-review dry-run."

        findings = []
        if not passed:
            findings.append(
                {
                    "id": "logic-breaker-1",
                    "lane": "logic_breaker",
                    "rule_id": rule_id,
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": "",
                    "line": 0,
                    "repro_command": " ".join(cmd),
                    "summary": summary,
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )

        return {
            "passed": passed,
            "repro_script": str(repro_script),
            "repro_command": " ".join(cmd),
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": timeout,
            "timeout_sec": LOGIC_BREAKER_TIMEOUT_SEC,
            "dependency_mode": "active_venv",
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "findings": findings,
        }

    def _run_ghost_regression(self, test_candidates: list[str], *, execution_root: Path) -> dict[str, Any]:
        if not test_candidates:
            return {
                "passed": True,
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": [],
                "findings": [],
                "execution_mode": "sandbox_mirror",
                "execution_cwd": str(execution_root),
                "timeout": False,
                "timeout_sec": GHOST_REGRESSION_TIMEOUT_SEC,
                "dependency_mode": "active_venv",
                "pytest_stdout_tail": "",
                "pytest_stderr_tail": "",
            }

        cmd = ["uv", "run", "--active", "pytest", "-q", *test_candidates]
        timeout = False
        try:
            result = subprocess.run(
                cmd,
                cwd=execution_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=GHOST_REGRESSION_TIMEOUT_SEC,
            )
            passed = result.returncode == 0
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            rule_id = "regression_test_failed"
            summary = "Ghost regression candidate failed in ultra-review dry-run."
        except subprocess.TimeoutExpired as exc:
            passed = False
            timeout = True
            stdout_tail = str(exc.output or "")[-2000:]
            stderr_tail = str(exc.stderr or "")[-2000:]
            rule_id = "regression_test_timeout"
            summary = "Ghost regression candidate timed out in ultra-review dry-run."
        failed_tests = [] if passed else list(test_candidates)
        findings = []
        if not passed:
            findings.append(
                {
                    "id": "ghost-regression-1",
                    "lane": "ghost_regression",
                    "rule_id": rule_id,
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": "",
                    "line": 0,
                    "repro_command": " ".join(cmd),
                    "summary": summary,
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )
        return {
            "passed": passed,
            "executed_tests": list(test_candidates),
            "failed_tests": failed_tests,
            "skipped_tests": [],
            "findings": findings,
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": timeout,
            "timeout_sec": GHOST_REGRESSION_TIMEOUT_SEC,
            "dependency_mode": "active_venv",
            "pytest_stdout_tail": stdout_tail,
            "pytest_stderr_tail": stderr_tail,
        }

    def _changed_files(self, diff_text: str) -> list[str]:
        files: list[str] = []
        for line in diff_text.splitlines():
            if not line.startswith("diff --git "):
                continue
            path = self._path_from_diff_header(line)
            if path:
                files.append(path)
        return files

    def _resolve(self, path: Path | str) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.project_root / path_obj).resolve()

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise UltraReviewError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    def _run_id(self) -> str:
        return "ultra-review-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
