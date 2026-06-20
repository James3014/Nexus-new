"""
MicroVerifier v1.0

Lightweight post-patch verification before the full verification phase.
Runs: syntax check → import check → target test check.
Catches issues early to avoid wasting 14B model calls on invalid patches.
"""
from __future__ import annotations

import ast
import subprocess
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


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
    
    @property
    def can_proceed_to_full_verifier(self) -> bool:
        return self.passed and self.syntax_ok


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
        verifier_env_metadata: Optional[Dict[str, Any]] = None
    ) -> MicroVerifyResult:
        """Run micro-verification on patched files."""
        meta = verifier_env_metadata or {}
        interpreter = meta.get("interpreter") or ""
        allow_bare_python = meta.get("allow_bare_python", False)
        pytest_cmd = meta.get("pytest_command") or ""
        
        classifications = []
        
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
            )
        
        # 2. Environment check & Import check
        # If no interpreter specified and bare python not allowed, fail closed.
        if not interpreter and not allow_bare_python:
            classifications.append("env_blocked")
            classifications.append("false_fail_risk")
            return MicroVerifyResult(
                passed=False,
                syntax_ok=True,
                error_message="ENV_BLOCKED",
                details="Interpreter not specified and bare python3 is not approved.",
                classifications=classifications,
            )

        cmd_interpreter = interpreter or "python3"
        if cmd_interpreter == "python3" and not allow_bare_python:
            classifications.append("env_blocked")
            return MicroVerifyResult(
                passed=False,
                syntax_ok=True,
                error_message="ENV_BLOCKED",
                details="Bare python3 is blocked by policy.",
                classifications=classifications,
            )
            
        import_ok = True
        import_errors = []
        for file_path in patched_files:
            if file_path.endswith(".py") and not file_path.startswith("test_"):
                full_path = repo_dir / file_path
                if full_path.exists():
                    rel_path = os.path.relpath(full_path, repo_dir)
                    module_name = os.path.splitext(rel_path)[0].replace(os.path.sep, ".")
                    try:
                        result = subprocess.run(
                            [cmd_interpreter, "-c", f"import sys; sys.path.insert(0, '{repo_dir}'); import {module_name}"],
                            capture_output=True, text=True, timeout=10,
                            cwd=str(repo_dir)
                        )
                        if result.returncode != 0:
                            import_ok = False
                            import_errors.append(f"{file_path}: {result.stderr[:200]}")
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
            )
            
        classifications.append("task_scoped_import_check")
        
        # 3. Target test check
        test_ok = True
        test_errors = []
        test_files = []
        for file_path in patched_files:
            if file_path.startswith("test_") or "_test.py" in file_path:
                test_files.append(file_path)
        
        if test_files:
            # Determine pytest executable
            run_cmd = []
            if pytest_cmd:
                run_cmd = [pytest_cmd]
            elif interpreter:
                run_cmd = [interpreter, "-m", "pytest"]
            else:
                run_cmd = ["python3", "-m", "pytest"]
                
            for test_file in test_files:
                full_path = repo_dir / test_file
                if full_path.exists():
                    try:
                        result = subprocess.run(
                            run_cmd + [str(full_path), "-x", "--tb=short", "-q"],
                            capture_output=True, text=True, timeout=30,
                            cwd=str(repo_dir)
                        )
                        if result.returncode != 0:
                            test_ok = False
                            test_errors.append(f"{test_file}: {result.stdout[-500:]}")
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
                import_ok=True,
                test_ok=False,
                error_message="TEST_FAILURE",
                details="\n".join(test_errors),
                interpreter_used=cmd_interpreter,
                classifications=classifications,
            )
            
        if test_files:
            classifications.append("verifier_command_check")
        else:
            # If no test files existed, we only did syntax + import.
            # Record false_pass_risk since we didn't run real tests.
            classifications.append("false_pass_risk")
            
        return MicroVerifyResult(
            passed=True,
            syntax_ok=True,
            import_ok=True,
            test_ok=True if test_files else False,
            interpreter_used=cmd_interpreter,
            classifications=classifications,
        )
