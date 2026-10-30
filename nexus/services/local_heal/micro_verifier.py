"""
MicroVerifier v1.0

Lightweight post-patch verification before the full verification phase.
Runs: syntax check → import check → target test check.
Catches issues early to avoid wasting 14B model calls on invalid patches.
"""
from __future__ import annotations

import ast
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional

from nexus.engine.model_output_sandbox import (
    SandboxError,
    interpreter_readable_roots,
    run_model_argv,
)

# Imports one module of the patched repo; the repo dir and module name arrive as argv, never
# interpolated into the code.
_IMPORT_PROBE = (
    "import importlib, sys; sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])"
)
# The same import for a test file (#2975 R1): if it fails only because pytest itself is not
# installed (the missing module is pytest/_pytest, and importing that package on its own fails
# the same way), print the marker instead of failing. Any other import error is re-raised (exit 1,
# fails closed); a missing ``pytest.<sub>`` while pytest imports is re-raised too.
_PYTEST_IMPORT_MISSING_MARKER = "NEXUS_MICRO_VERIFY_TEST_IMPORT_NEEDS_PYTEST"
_TEST_IMPORT_PROBE = (
    "import importlib, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "try:\n"
    "    importlib.import_module(sys.argv[2])\n"
    "except ModuleNotFoundError as e:\n"
    "    root = (e.name or '').partition('.')[0]\n"
    "    if root not in ('pytest', '_pytest'):\n"
    "        raise\n"
    "    try:\n"
    "        importlib.import_module(root)\n"
    "    except ModuleNotFoundError as again:\n"
    "        if again.name != root:\n"
    "            raise e\n"
    "    else:\n"
    "        raise e\n"
    f"    print('{_PYTEST_IMPORT_MISSING_MARKER}')\n"
)

# Asks the interpreter whether it can import pytest at all, without importing it (#2975). Exit 0
# with the marker = absent (step skipped); exit 0 without it = present (pytest runs); a non-zero
# exit or an error = the probe failed (fails closed).
_PYTEST_ABSENT_MARKER = "NEXUS_MICRO_VERIFY_PYTEST_ABSENT"
_PYTEST_PROBE = (
    "import importlib.util; "
    f"print('' if importlib.util.find_spec('pytest') else '{_PYTEST_ABSENT_MARKER}')"
)
# pytest's documented exit status for "no tests were collected".
_PYTEST_NO_TESTS_COLLECTED = 5


def _error_summary(stderr: str) -> str:
    """The exception line first (the cause), then a bounded tail of the traceback (#2975 R2)."""
    lines = [line for line in (stderr or "").strip().splitlines() if line.strip()]
    if not lines:
        return "(no stderr)"
    tail = "\n".join(lines[:-1])[-400:]
    return lines[-1][:300] + (f"\n{tail}" if tail else "")


def is_test_file(file_path: str) -> bool:
    """pytest's default ``python_files`` names: ``test_*.py`` or ``*_test.py`` (basename)."""
    name = PurePath(file_path).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


@dataclass
class MicroVerifyResult:
    """Result of micro-verification."""
    passed: bool
    syntax_ok: bool = False
    import_ok: bool = False
    test_ok: bool = False
    error_message: str = ""
    details: str = ""
    interpreter_used: str = ""
    classifications: List[str] = field(default_factory=list)
    task_scoped: bool = False  # T2: Whether task-scoped verifier was used
    # #2975: what the target-test step did: "not_applicable" (no test files), "ran",
    # "failed", or "skipped" with test_skip_reason ("pytest_unavailable", "no_tests_collected").
    test_step: str = "not_applicable"
    test_skip_reason: str = ""
    test_files: List[str] = field(default_factory=list)
    no_tests_collected: List[str] = field(default_factory=list)
    # #2975 R1: test files whose import check could not run only because pytest is missing.
    import_skipped: List[str] = field(default_factory=list)

    @property
    def can_proceed_to_full_verifier(self) -> bool:
        return self.passed and self.syntax_ok

    def receipt_fields(self) -> Dict[str, Any]:
        """Compact record for the patch attempt receipt (a skipped step stays visible)."""
        return {
            "passed": self.passed,
            "error_message": self.error_message,
            "interpreter": self.interpreter_used,
            "test_step": self.test_step,
            "test_skip_reason": self.test_skip_reason,
            "test_files": list(self.test_files),
            "no_tests_collected": list(self.no_tests_collected),
            "classifications": list(self.classifications),
            # Only when it happened, so receipts without a skipped import keep their shape.
            **({"import_skipped": list(self.import_skipped)} if self.import_skipped else {}),
        }


class MicroVerifier:
    """
    Lightweight post-patch verifier.
    Runs quick checks before the full verification phase to catch obvious issues.
    """
    
    @staticmethod
    def verify(
        patch_content: str, 
        repo_dir: Path, 
        patched_files: List[str], 
        verifier_env_metadata: Optional[Dict[str, Any]] = None,
        env_taxonomy: Optional[Dict[str, Any]] = None,
    ) -> MicroVerifyResult:
        """Run micro-verification on patched files.

        Args:
            verifier_env_metadata: Task-scoped env metadata (interpreter, pytest_command, etc.)
            env_taxonomy: Env taxonomy classification for this task (from EnvFailureTaxonomy)
        """
        meta = verifier_env_metadata or {}
        env_tax = env_taxonomy or {}
        interpreter = meta.get("interpreter") or ""
        allow_bare_python = meta.get("allow_bare_python", False)
        pytest_cmd = meta.get("pytest_command") or ""
        
        # T2: Determine task-scoped interpreter from env taxonomy ONLY
        # env_taxonomy is the authoritative source for task-scoped context.
        # Raw metadata interpreter is NOT task-scoped — it's a fallback hint.
        task_scoped = False
        task_interpreter = ""
        if env_tax.get("interpreter"):
            task_interpreter = env_tax["interpreter"]
            task_scoped = True
        elif env_tax.get("verifier_command"):
            task_interpreter = env_tax["verifier_command"]
            task_scoped = True
        
        # T2: Fail closed if no task-scoped context and bare python not allowed
        if not task_scoped and not interpreter and not allow_bare_python:
            classifications_detail = ["env_blocked", "false_fail_risk", "micro_verify_context_missing"]
            return MicroVerifyResult(
                passed=False,
                syntax_ok=False,
                error_message="MICRO_VERIFY_CONTEXT_MISSING",
                details="No task-scoped interpreter or verifier command available. "
                        "Bare python3 is not approved. Cannot proceed with verification.",
                classifications=classifications_detail,
                task_scoped=False,
            )
        
        # Use metadata interpreter as fallback (not task-scoped)
        cmd_interpreter = task_interpreter or interpreter or "python3"
        
        # T2: If bare python3 is the only option, classify as env_blocked
        if cmd_interpreter == "python3" and not allow_bare_python and not task_scoped:
            return MicroVerifyResult(
                passed=False,
                syntax_ok=False,
                error_message="ENV_BLOCKED",
                details="Bare python3 is blocked by policy. Task-scoped verifier required.",
                classifications=["env_blocked", "false_fail_risk"],
                task_scoped=False,
            )
        
        classifications = []
        if task_scoped:
            classifications.append("task_scoped_verifier")
            
        # 1. Syntax check on patched files (generic AST parse)
        syntax_ok = True
        syntax_errors = []
        for file_path in patched_files:
            full_path = repo_dir / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    ast.parse(content)
                except SyntaxError as e:
                    syntax_ok = False
                    syntax_errors.append(f"{file_path}:{e.lineno}: {e.msg}")
        
        if syntax_ok:
            classifications.append("syntax_parse_check")
        else:
            classifications.append("syntax_parse_failed")
            return MicroVerifyResult(
                passed=False,
                syntax_ok=False,
                error_message="SYNTAX_ERROR",
                details="\n".join(syntax_errors),
                classifications=classifications,
                task_scoped=task_scoped,
            )
            
        import_ok = True
        import_errors = []
        import_skipped: List[str] = []
        for file_path in patched_files:
            if file_path.endswith(".py") and not file_path.startswith("test_"):
                full_path = repo_dir / file_path
                if full_path.exists():
                    rel_path = os.path.relpath(full_path, repo_dir)
                    module_name = os.path.splitext(rel_path)[0].replace(os.path.sep, ".")
                    test_module = is_test_file(file_path)
                    probe_code = _TEST_IMPORT_PROBE if test_module else _IMPORT_PROBE
                    try:
                        # Importing runs the model-written patch: OS sandbox, no network, writes
                        # only in repo_dir; no barrier means nothing runs (#2945).
                        result = run_model_argv(
                            [cmd_interpreter, "-c", probe_code, str(repo_dir), module_name],
                            work_dir=repo_dir,
                            timeout=10,
                            readable=interpreter_readable_roots(cmd_interpreter),
                        )
                        if result.returncode != 0:
                            import_ok = False
                            import_errors.append(f"{file_path}: {_error_summary(result.stderr)}")
                        elif test_module and _PYTEST_IMPORT_MISSING_MARKER in result.stdout:
                            # #2975 R1: the test module needs pytest and this interpreter has none.
                            # Not a patch error; recorded, and the test step below still probes
                            # pytest and either runs the file or records its own skip.
                            import_skipped.append(file_path)
                    except SandboxError as e:
                        import_ok = False
                        classifications.append("verifier_unavailable")
                        import_errors.append(f"verifier_sandbox_unavailable: {e}")
                    except FileNotFoundError:
                        import_ok = False
                        classifications.append("verifier_unavailable")
                        import_errors.append(f"Interpreter {cmd_interpreter} not found.")
                    except Exception as e:
                        import_ok = False
                        import_errors.append(str(e))
        
        if not import_ok:
            classifications.append("import_failed")
            if "verifier_unavailable" not in classifications:
                classifications.append("false_fail_risk")
            return MicroVerifyResult(
                passed=False,
                syntax_ok=True,
                import_ok=False,
                error_message="IMPORT_ERROR",
                details="\n".join(import_errors),
                interpreter_used=cmd_interpreter,
                classifications=classifications,
                task_scoped=task_scoped,
                import_skipped=import_skipped,
            )
            
        classifications.append("task_scoped_import_check")
        
        # 3. Target test check
        test_ok = True
        test_errors = []
        test_files = [file_path for file_path in patched_files if is_test_file(file_path)]
        test_skip_reason = ""
        tests_collected = 0
        no_tests_collected: List[str] = []

        if test_files:
            # Determine pytest executable — prefer task-scoped
            run_cmd = []
            if pytest_cmd:
                run_cmd = [pytest_cmd]
            elif task_interpreter:
                run_cmd = [task_interpreter, "-m", "pytest"]
            elif interpreter:
                run_cmd = [interpreter, "-m", "pytest"]
            else:
                run_cmd = ["python3", "-m", "pytest"]

            # #2975: `<interpreter> -m pytest` on an interpreter without pytest is not a test
            # failure. Ask first; when pytest is absent, record the step as skipped (the full
            # verifier still decides). A probe that cannot run or answers oddly fails closed.
            if not pytest_cmd:
                try:
                    probe = run_model_argv(
                        [run_cmd[0], "-c", _PYTEST_PROBE],
                        work_dir=repo_dir,
                        timeout=10,
                        readable=interpreter_readable_roots(run_cmd[0]),
                    )
                    if probe.returncode != 0:
                        test_ok = False
                        classifications.append("verifier_unavailable")
                        test_errors.append(
                            f"pytest_probe_failed: exit {probe.returncode}: {probe.stderr[-300:]}"
                        )
                    elif _PYTEST_ABSENT_MARKER in probe.stdout:
                        test_skip_reason = "pytest_unavailable"
                except SandboxError as e:
                    test_ok = False
                    classifications.append("verifier_unavailable")
                    test_errors.append(f"verifier_sandbox_unavailable: {e}")
                except FileNotFoundError:
                    test_ok = False
                    classifications.append("verifier_unavailable")
                    test_errors.append(f"Interpreter {run_cmd[0]} not found.")
                except subprocess.TimeoutExpired:
                    test_ok = False
                    classifications.append("verifier_unavailable")
                    test_errors.append("Timeout expired during pytest probe.")
                except Exception as e:
                    test_ok = False
                    classifications.append("verifier_unavailable")
                    test_errors.append(f"pytest_probe_failed: {e}")

            for test_file in test_files if test_ok and not test_skip_reason else []:
                full_path = repo_dir / test_file
                if full_path.exists():
                    try:
                        # The patched repo's tests (and any conftest.py in it) are model output.
                        result = run_model_argv(
                            run_cmd + [str(full_path), "-x", "--tb=short", "-q"],
                            work_dir=repo_dir,
                            timeout=30,
                            readable=interpreter_readable_roots(run_cmd[0]),
                        )
                        if result.returncode == _PYTEST_NO_TESTS_COLLECTED:
                            # A *_test.py module with no tests in it (#2975): not a failure,
                            # but recorded so the receipt never claims it ran.
                            no_tests_collected.append(test_file)
                            continue
                        if result.returncode != 0:
                            test_ok = False
                            test_errors.append(
                                f"{test_file}: {result.stdout[-500:]}{result.stderr[-500:]}"
                            )
                        else:
                            tests_collected += 1
                    except SandboxError as e:
                        test_ok = False
                        classifications.append("verifier_unavailable")
                        test_errors.append(f"verifier_sandbox_unavailable: {e}")
                    except FileNotFoundError:
                        test_ok = False
                        classifications.append("verifier_unavailable")
                        test_errors.append(f"Pytest executable not found: {run_cmd}")
                    except subprocess.TimeoutExpired:
                        test_ok = False
                        classifications.append("false_fail_risk")
                        test_errors.append(f"Timeout expired during test run.")
                    except Exception as e:
                        test_ok = False
                        test_errors.append(str(e))
        
        if not test_ok:
            classifications.append("test_failed")
            if "verifier_unavailable" not in classifications and "false_fail_risk" not in classifications:
                classifications.append("false_fail_risk")
            return MicroVerifyResult(
                passed=False,
                syntax_ok=True,
                import_ok=not import_skipped,
                test_ok=False,
                error_message="TEST_FAILURE",
                details="\n".join(test_errors),
                interpreter_used=cmd_interpreter,
                classifications=classifications,
                task_scoped=task_scoped,
                test_step="failed",
                test_files=test_files,
                import_skipped=import_skipped,
            )

        if test_files and not test_skip_reason and tests_collected == 0:
            test_skip_reason = "no_tests_collected"

        details = ""
        if test_skip_reason:
            # Degraded to syntax + import only; visible in the result and the receipt.
            test_step = "skipped"
            classifications.extend(["test_step_skipped", test_skip_reason, "false_pass_risk"])
            details = f"test step skipped: {test_skip_reason} ({', '.join(test_files)})"
        elif test_files:
            test_step = "ran"
            classifications.append("verifier_command_check")
            if no_tests_collected:
                classifications.extend(["no_tests_collected", "false_pass_risk"])
                details = f"no tests collected: {', '.join(no_tests_collected)}"
        else:
            # If no test files existed, we only did syntax + import.
            # Record false_pass_risk since we didn't run real tests.
            test_step = "not_applicable"
            classifications.append("false_pass_risk")

        if import_skipped:
            classifications.append("import_step_skipped")
            if test_step != "ran" and "false_pass_risk" not in classifications:
                classifications.append("false_pass_risk")
            skipped_note = f"import check skipped (pytest_unavailable): {', '.join(import_skipped)}"
            details = f"{details}\n{skipped_note}" if details else skipped_note

        return MicroVerifyResult(
            passed=True,
            syntax_ok=True,
            import_ok=not import_skipped,
            test_ok=test_step == "ran",
            details=details,
            interpreter_used=cmd_interpreter,
            classifications=classifications,
            task_scoped=task_scoped,
            test_step=test_step,
            test_skip_reason=test_skip_reason,
            test_files=test_files,
            no_tests_collected=no_tests_collected,
            import_skipped=import_skipped,
        )
