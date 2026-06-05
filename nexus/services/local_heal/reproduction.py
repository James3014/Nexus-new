import subprocess
import os
import re
import inspect
from pathlib import Path
from typing import Any, Tuple

class ReproductionRunner:
    """🧪 ReproductionRunner: 負責建立物理失敗證據 (Nexus v2.9 Hardened)"""
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

    def run_repro(self, script_code: str) -> Tuple[bool, str]:
        if not script_code: return False, "No repro script."
        script_code = self.clean_repro_script(script_code)
        if "```" in script_code:
            return False, "Invalid repro script: markdown fence remains after sanitization."
        repro_path = self.repo_dir / "reproduce_bug.py"
        try:
            # 硬化：路徑注入必須在最前面，否則會載入到 venv 裡已安裝的 astropy
            benchmarks_dir = str(self.repo_dir / "scripts/benchmarks")
            path_injection = (
                "import sys, os\n"
                f"sys.path.insert(0, {str(self.repo_dir)!r})\n"
                f"sys.path.insert(1, {benchmarks_dir!r})\n"
            )
            repro_path.write_text(path_injection + script_code, encoding="utf-8")

            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            env.pop("VIRTUAL_ENV", None)

            # 使用 -I (Isolated) 模式
            res = subprocess.run(
                [self.python_executable, "-I", "reproduce_bug.py"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )

            output = res.stdout + res.stderr
            if res.returncode != 0:
                if self.is_environment_failure(output):
                    return False, output if output.strip() else f"Process exited with code {res.returncode}"
                return True, output if output.strip() else f"Process exited with code {res.returncode}"
            return False, output
        except Exception as e:
            return False, str(e)
        finally:
            # 暫時保留腳本以供偵錯
            pass
            # if repro_path.exists():
            #     try: os.remove(repro_path)
            #     except: pass
