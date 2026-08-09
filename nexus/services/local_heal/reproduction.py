import ast
import hashlib
import inspect
import json
import os
import re
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Any, Tuple


class SyntaxValidator:
    """🔍 SyntaxValidator: 靜態 Python 語法驗證器，實踐 Fail-Fast 原則"""
    @staticmethod
    def validate_syntax(code: str) -> Tuple[bool, str | None]:
        try:
            ast.parse(code)
            return True, None
        except (SyntaxError, IndentationError) as e:
            tb = "".join(traceback.format_exception_only(type(e), e))
            return False, tb.strip()


class ReproductionRunner:
    """🧪 ReproductionRunner: 負責建立物理失敗證據 (Nexus v2.9 Hardened)"""
    _FAILURE_RECORD_ENV = "NEXUS_REPRO_FAILURE_RECORD_PATH"
    def __init__(
        self,
        repo_dir: Path,
        generate_fn: Any = None,
        model_name: str | None = None,
        timeout_seconds: int | None = None,
        python_executable: str = "python3",
    ):
        self.repo_dir = repo_dir
        self.generate_fn = generate_fn
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable
        self.last_exit_status: int | None = None
        self.last_reason_code = "not_run"
        self.last_command: tuple[str, ...] = ()
        self.last_script_sha256 = ""

    def workspace_identity(self) -> tuple[str, bool]:
        """Bind source identity to Git HEAD and tamper-sensitive workspace state."""
        try:
            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", *args], cwd=str(self.repo_dir), capture_output=True,
                    text=True, check=True,
                )
                return result.stdout

            head = git("rev-parse", "HEAD").strip()
            status = git("status", "--porcelain=v1", "--untracked-files=all")
            tracked_diff = git("diff", "--binary")
            staged_diff = git("diff", "--cached", "--binary")
            untracked = []
            for line in status.splitlines():
                if line.startswith("?? "):
                    path = self.repo_dir / line[3:]
                    untracked.append((line[3:], path.read_bytes()))
            payload = repr((head, status, tracked_diff, staged_diff, untracked)).encode("utf-8")
            digest = hashlib.sha256(payload).hexdigest()
            return f"HEAD={head};WORKSPACE_SHA256={digest}", True
        except (OSError, subprocess.SubprocessError, UnicodeError):
            return "", False

    @staticmethod
    def clean_repro_script(script: str) -> str:
        script = script.strip()
        fenced = re.search(r"```(?:python|py)?\s*\n(.*?)\n\s*```", script, re.DOTALL | re.IGNORECASE)
        if fenced:
            script = fenced.group(1)
        script = re.sub(r"^\s*```(?:python|py)?\s*\n?", "", script, flags=re.IGNORECASE)
        script = re.sub(r"\n?\s*```\s*$", "", script)
        return script.strip()

    @staticmethod
    def _looks_like_python_reproducer(script: str) -> bool:
        lowered = script.lower()
        if "<<<<<<<" in script or "search:" in lowered or "replace:" in lowered:
            return False
        if not bool(re.search(r"\b(import|from|assert|raise|def|class|pytest|unittest|test_)\b", script)):
            return False
        failure_markers = (
            "assert",
            "raise",
            "sys.exit",
            "exit(",
            "pytest",
            "unittest",
            "test_challenge",
        )
        return any(marker in lowered for marker in failure_markers)

    def _extract_fenced_script(self, problem: str) -> str:
        candidates = []
        for match in re.finditer(r"```(?P<lang>[A-Za-z0-9_-]*)\s*\n(?P<body>.*?)\n\s*```", problem, re.DOTALL):
            lang = match.group("lang").lower()
            body = match.group("body").strip()
            if lang not in {"", "python", "py"}:
                continue
            if self._looks_like_python_reproducer(body):
                candidates.append(body)
        if candidates:
            return self.clean_repro_script(candidates[0])
        return ""

    def _call_generator(self, system_prompt: str, user_prompt: str) -> str:
        if not self.generate_fn:
            return ""
        try:
            sig = inspect.signature(self.generate_fn)
            if "model" in sig.parameters:
                kwargs = {"model": self.model_name}
                if "timeout" in sig.parameters and self.timeout_seconds is not None:
                    kwargs["timeout"] = self.timeout_seconds
                return self.generate_fn(system_prompt, user_prompt, **kwargs)
        except (TypeError, ValueError):
            pass
        return self.generate_fn(system_prompt, user_prompt)

    @staticmethod
    def is_environment_failure(output: str) -> bool:
        lowered = output.lower()
        env_markers = [
            "trying to import astropy from within a source checkout",
            "extension modules are built",
            "build_ext --inplace",
            "cannot import name '_compiler' from 'astropy.utils'",
            "numpy._core._multiarray_umath",
            "importing the numpy c-extensions failed",
            "no module named 'extension_helpers'",
            "no module named 'numpy'",
            "importerror: cannot import name",
            "partially initialized module",
            "circular import",
            "modulenotfounderror",
            "nameerror: name 'np' is not defined",
            "nameerror: name 'numpy' is not defined",
            "nameerror: name 'astropy' is not defined",
        ]
        return any(marker in lowered for marker in env_markers)

    def generate_repro_script(self, problem: str) -> str:
        embedded_script = self._extract_fenced_script(problem)
        if embedded_script:
            return embedded_script

        # 如果是本地併發題，我們直接讀取檔案並調用其測試函數
        # 這裡未來應由模型生成，目前針對本地模式優化
        match = re.search(r'([a-zA-Z0-9_./-]+\.py)', problem)
        if match:
            target_file = match.group(1)
            return (
                "import importlib.util\n"
                "from pathlib import Path\n\n"
                f"target = Path({target_file!r})\n"
                "if not target.is_absolute():\n"
                "    target = Path.cwd() / target\n"
                "spec = importlib.util.spec_from_file_location('nexus_repro_target', target)\n"
                "module = importlib.util.module_from_spec(spec)\n"
                "assert spec and spec.loader\n"
                "spec.loader.exec_module(module)\n"
                "try:\n"
                "    module.test_challenge()\n"
                "    print('SUCCESS')\n"
                "except AssertionError as e:\n"
                "    print(f'FAILURE: {e}')\n"
                "    exit(1)\n"
                "except Exception as e:\n"
                "    print(f'ERROR: {e}')\n"
                "    exit(1)"
            )

        generated = self._call_generator(
            "You write minimal Python bug reproduction scripts.",
            (
                "Write a single Python script that reproduces the issue below. "
                "Output only Python code, no markdown fences, no explanation. "
                "CRITICAL: The script must use explicit 'assert' statements, raise exceptions, "
                "or perform check-failed verifications so that it guarantees exiting with a "
                "non-zero status when the bug is present.\n\n"
                f"Issue:\n{problem}"
            ),
        )
        return self.clean_repro_script(generated) if generated else ""

    @classmethod
    def _execution_wrapper(cls, path_injection: str, script_code: str) -> str:
        wrapper = (
            path_injection
            + "import json as _nexus_json, traceback as _nexus_traceback\n"
            + f"_nexus_record_path = os.environ.pop({cls._FAILURE_RECORD_ENV!r}, '')\n"
            + f"_nexus_source = {script_code!r}\n"
            + "_nexus_globals = {\n"
            + "    '__name__': '__main__',\n"
            + "    '__file__': 'nexus_repro_contract.py',\n"
            + "    '_nexus_source': _nexus_source,\n"
            + "}\n"
            + "try:\n"
            + "    exec(compile(_nexus_source, 'nexus_repro_contract.py', 'exec'), _nexus_globals, _nexus_globals)\n"
            + "except BaseException as _nexus_exc:\n"
            + "    _nexus_frames = _nexus_traceback.extract_tb(_nexus_exc.__traceback__)\n"
            + "    _nexus_frame = _nexus_frames[-1] if _nexus_frames else None\n"
            + "    _nexus_code = getattr(_nexus_exc, 'code', None)\n"
            + "    if not isinstance(_nexus_code, (int, str, type(None))):\n"
            + "        _nexus_code = repr(_nexus_code)\n"
            + "    _nexus_payload = {\n"
            + "        'exception_type': type(_nexus_exc).__name__,\n"
            + "        'filename': _nexus_frame.filename if _nexus_frame else '',\n"
            + "        'lineno': _nexus_frame.lineno if _nexus_frame else 0,\n"
            + "        'exit_code': _nexus_code,\n"
            + "    }\n"
            + "    if _nexus_record_path:\n"
            + "        with open(_nexus_record_path, 'w', encoding='utf-8') as _nexus_record:\n"
            + "            _nexus_json.dump(_nexus_payload, _nexus_record, sort_keys=True)\n"
            + "    raise\n"
        )
        return wrapper

    @staticmethod
    def _failure_record(record_path: Path) -> dict[str, Any] | None:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return record if isinstance(record, dict) else None

    @staticmethod
    def _has_explicit_reproduction_contract(
        script_code: str,
        output: str,
        returncode: int,
        failure_record: dict[str, Any] | None,
    ) -> bool:
        if not failure_record:
            return False
        exception_type = failure_record.get("exception_type")
        if exception_type == "AssertionError":
            return True
        recorded_exit_code = failure_record.get("exit_code")
        if (
            exception_type != "SystemExit"
            or type(recorded_exit_code) is not int
            or type(returncode) is not int
            or recorded_exit_code != returncode
        ):
            return False
        if failure_record.get("filename") != "nexus_repro_contract.py":
            return False
        lineno = failure_record.get("lineno")
        if not isinstance(lineno, int):
            return False
        try:
            tree = ast.parse(script_code)
        except SyntaxError:
            return False
        has_explicit_nonzero_exit = any(
            isinstance(node, ast.Call)
            and node.lineno == lineno
            and isinstance(node.func, (ast.Name, ast.Attribute))
            and getattr(node.func, "id", getattr(node.func, "attr", "")) == "exit"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and type(node.args[0].value) is int
            and node.args[0].value != 0
            for node in ast.walk(tree)
        )
        return has_explicit_nonzero_exit and any(
            marker in output for marker in ("FAILURE:", "ERROR:")
        )

    def run_repro(self, script_code: str) -> Tuple[bool, str]:
        self.last_exit_status = None
        self.last_reason_code = "pre_subprocess_failure"
        self.last_command = ()
        self.last_script_sha256 = ""
        if not script_code:
            return False, "No repro script."
        script_code = self.clean_repro_script(script_code)
        if "```" in script_code:
            return False, "Invalid repro script: markdown fence remains after sanitization."

        # 靜態語法檢查 Fail-Fast 防線
        is_valid, err_msg = SyntaxValidator.validate_syntax(script_code)
        if not is_valid:
            return False, f"SyntaxError in generated script:\n{err_msg}"

        repro_path = self.repo_dir / "reproduce_bug.py"
        subprocess_started = False
        record_path: Path | None = None
        try:
            # 硬化：路徑注入必須在最前面，否則會載入到 venv 裡已安裝的 astropy
            benchmarks_dir = str(self.repo_dir / "scripts/benchmarks")
            path_injection = (
                "import sys, os\n"
                f"sys.path.insert(0, {str(self.repo_dir)!r})\n"
                f"sys.path.insert(1, {benchmarks_dir!r})\n"
            )
            executed_script = self._execution_wrapper(path_injection, script_code)
            repro_path.write_text(executed_script, encoding="utf-8")
            self.last_script_sha256 = hashlib.sha256(executed_script.encode("utf-8")).hexdigest()

            record_fd, raw_record_path = tempfile.mkstemp(prefix="nexus-repro-failure-", suffix=".json")
            os.close(record_fd)
            os.unlink(raw_record_path)
            record_path = Path(raw_record_path)
            execution_env = os.environ.copy()
            execution_env[self._FAILURE_RECORD_ENV] = str(record_path)

            # 不使用 -I 模式以利繼承環境
            repro_run_timeout = int(os.environ.get("NEXUS_REPRO_RUN_TIMEOUT_SECONDS", "180"))
            self.last_command = (self.python_executable, "reproduce_bug.py")
            subprocess_started = True
            res = subprocess.run(
                [self.python_executable, "reproduce_bug.py"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=repro_run_timeout,
                env=execution_env
            )
            self.last_exit_status = res.returncode

            output = res.stdout + res.stderr
            failure_record = self._failure_record(record_path)
            if res.returncode != 0:
                if self.is_environment_failure(output):
                    self.last_reason_code = "environment_failure"
                    return False, output if output.strip() else f"Process exited with code {res.returncode}"
                if self._has_explicit_reproduction_contract(
                    script_code, output, res.returncode, failure_record
                ):
                    self.last_reason_code = "physical_fail"
                    return True, output if output.strip() else f"Process exited with code {res.returncode}"
                self.last_reason_code = "unclassified_nonzero_exit"
                return False, output if output.strip() else f"Process exited with code {res.returncode}"
            # Exit code 0: script ran successfully
            self.last_reason_code = "physical_not_reproduced"
            # If there's no error output, the bug might already be fixed
            if not output.strip():
                return False, "ALREADY_FIXED: reproduce script exited cleanly (exit code 0), bug may already be resolved"
            return False, output
        except subprocess.TimeoutExpired as e:
            self.last_reason_code = "execution_timeout"
            return False, str(e)
        except Exception as e:
            self.last_reason_code = "execution_exception" if subprocess_started else "pre_subprocess_failure"
            return False, str(e)
        finally:
            if record_path is not None:
                try:
                    record_path.unlink(missing_ok=True)
                except OSError:
                    pass
            # 暫時保留腳本以供偵錯
            pass
            # if repro_path.exists():
            #     try: os.remove(repro_path)
            #     except: pass
