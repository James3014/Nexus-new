"""CLI Pre-Gate：在 A 階段之前，用 exit code 做一次機械性驗證"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import json
from types import SimpleNamespace
from nexus.engine.target_env_context import TargetEnvContext

logger = logging.getLogger(__name__)

def _get_venv_python(project_root: Path) -> str:
    """
    💎 物理直譯器鎖定 (Iron Python):
    優先尋找虛擬環境直譯器。
    """
    # Mac/Linux
    python_bin = project_root / ".venv" / "bin" / "python3"
    if not python_bin.exists():
        # Windows
        python_bin = project_root / ".venv" / "Scripts" / "python.exe"
    
    if python_bin.exists():
        return str(python_bin)
    
    return sys.executable

_PREGATE_OPERATORS = frozenset({";", "&&", "||", "|", "<", ">", "&", ">>", "2>", "&>"})
_PREGATE_PYTHON_RE = re.compile(r"python[0-9.]*(\.exe)?")
_PREGATE_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PREGATE_ENV_ALLOWLIST = frozenset({"LANG", "LC_ALL", "PATH", "PYTHONPATH", "TMPDIR", "VIRTUAL_ENV"})


def _build_pregate_request(cmd: str, cwd: Path, env_overlay: dict, timeout: float = 60.0):
    """Tokenize ``cmd`` WITHOUT a shell and build a governed CliWorkerRequest.

    The request goes through the same no-shell launcher, forbidden-subcommand
    denylist, GitHub credential stripping and isolated HOME as every other
    verifier/worker spawn.  Raises ValueError when the command needs a shell.
    """
    from nexus.executors.cli_worker import CliWorkerRequest
    from nexus.executors.exec_policy import is_forwarder_executable

    tokens = list(shlex.split(cmd))
    # ``2>&1`` is the only redirection used by generated commands; stderr is
    # captured separately by the launcher, so it is dropped rather than shelled.
    tokens = [token for token in tokens if token != "2>&1"]
    if not tokens:
        raise ValueError("empty pregate command")
    if any(_PREGATE_ENV_ASSIGNMENT_RE.match(token) for token in tokens[:1]):
        raise ValueError("environment assignments are not allowed in pregate commands")
    executable, args = tokens[0], tokens[1:]
    name = Path(executable).name.lower()
    if is_forwarder_executable(executable):
        raise ValueError("shell and shell-forwarding executables are not allowed")
    python_code = _PREGATE_PYTHON_RE.fullmatch(name) is not None
    for index, token in enumerate(args):
        if token in _PREGATE_OPERATORS:
            raise ValueError("shell operators are not allowed in pregate commands")
        exempt = python_code and index > 0 and args[index - 1] == "-c"
        if "\x00" in token or (any(ch in token for ch in ";&|<>()$`") and not exempt):
            raise ValueError("shell metacharacters are not allowed in pregate arguments")
    path = env_overlay.get("PATH")
    resolved = shutil.which(executable, path=path) if path else None
    return CliWorkerRequest(
        executable=resolved or executable,
        argv=tuple(args),
        cwd=str(cwd),
        timeout_seconds=float(timeout),
        env=env_overlay,
    )


def run_cli_pregate(
    project_root: Path | str | TargetEnvContext,
    commands: List[str],
    timeout_per_cmd: int = 60,
) -> Tuple[bool, List[dict]]:
    """
    執行驗證指令列表，回傳 (all_passed, results)
    """
    if isinstance(project_root, TargetEnvContext):
        target_repo_root = project_root.target_repo_root
        target_venv = project_root.target_venv
    else:
        target_repo_root = Path(project_root)
        target_venv = target_repo_root / ".venv"

    if not commands:
        # === CHANGED: 空指令 → UNVERIFIED（非 pass） ===
        return False, [{
            "cmd": "_NO_VERIFY_COMMANDS",
            "exit_code": -1,
            "passed": False,
            "pregate_skip": True,
            "reason": "No verification commands detected. Cannot confirm repair success."
        }]
    
    # 🔍 Sanitization: Replace polluted absolute engine python path with relative python3/python
    sanitized_commands = []
    engine_venv_python = str(Path(sys.executable).resolve())
    for cmd in commands:
        if engine_venv_python in cmd:
            cmd = cmd.replace(engine_venv_python, "python3")
        engine_default_venv = "/Users/jameschen/Workspace/nexus/.venv/bin/python3"
        if engine_default_venv in cmd:
            cmd = cmd.replace(engine_default_venv, "python3")
        sanitized_commands.append(cmd)
    commands = sanitized_commands
    
    env = {key: value for key, value in os.environ.items() if key in _PREGATE_ENV_ALLOWLIST}
    if target_venv:
        # Mac/Linux
        venv_bin = target_venv / "bin"
        if not venv_bin.exists():
            # Windows
            venv_bin = target_venv / "Scripts"
        venv_bin_str = str(venv_bin)
    else:
        venv_bin_str = str(target_repo_root / ".venv" / "bin")
        
    env["PATH"] = f"{venv_bin_str}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = f"{target_repo_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
    
    results = []
    all_passed = True
    
    for cmd in commands:
        try:
            logger.info("🧪 [Pre-Gate] 執行驗證: %s", cmd)
            from nexus.executors.cli_worker import CliWorkerStatus, run_cli_worker

            try:
                request = _build_pregate_request(cmd, target_repo_root, env, timeout_per_cmd)
            except ValueError as exc:
                results.append({
                    "cmd": cmd,
                    "exit_code": -1,
                    "passed": False,
                    "stderr_tail": f"pregate command rejected: {exc}",
                })
                all_passed = False
                logger.warning("❌ CLI Pre-Gate REJECTED: %s (%s)", cmd, exc)
                continue
            worker = run_cli_worker(request)
            if worker.status is CliWorkerStatus.TIMED_OUT:
                raise subprocess.TimeoutExpired(cmd, timeout_per_cmd)
            if worker.status is CliWorkerStatus.START_FAILED or worker.exit_code is None:
                results.append({
                    "cmd": cmd,
                    "exit_code": -1,
                    "passed": False,
                    "stderr_tail": worker.stderr.decode("utf-8", errors="replace")[-500:],
                })
                all_passed = False
                continue

            proc = SimpleNamespace(
                returncode=worker.exit_code,
                stdout=worker.stdout.decode("utf-8", errors="replace"),
                stderr=worker.stderr.decode("utf-8", errors="replace"),
            )

            # ⚖️ 治理門檻調整 (Adaptive Gating):
            # rc == 2 (Usage error/Path not found in Sandbox) 不再視為 Soft Fail (passed)。
            is_env_error = (proc.returncode == 2)
            passed = (proc.returncode == 0)
            if is_env_error:
                logger.warning("⚠️ CLI Pre-Gate SOFT FAIL (rc=2): %s — Counted as FAIL.", cmd)
            
            results.append({
                "cmd": cmd,
                "exit_code": proc.returncode,
                "passed": passed,
                "is_soft_fail": is_env_error,
                "stdout_tail": (proc.stdout or "")[-500:],
                "stderr_tail": (proc.stderr or "")[-500:],
            })
            
            if not passed:
                all_passed = False
                if is_env_error:
                    logger.warning("⚠️ CLI Pre-Gate SOFT FAIL (rc=2, Ambient Noise): %s", cmd)
                else:
                    logger.warning("❌ CLI Pre-Gate FAIL: %s (rc=%d)", cmd, proc.returncode)
            else:
                logger.info("✅ CLI Pre-Gate PASS: %s", cmd)
                
        except subprocess.TimeoutExpired:
            results.append({
                "cmd": cmd,
                "exit_code": 124,
                "passed": False,
                "stderr_tail": f"timeout after {timeout_per_cmd}s",
            })
            all_passed = False
            logger.warning("❌ CLI Pre-Gate TIMEOUT: %s", cmd)
    
    return all_passed, results

def detect_project_language(root: Path) -> set[str]:
    """根據目錄中的檔案偵測專案語言"""
    langs = set()
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "requirements.txt").exists():
        langs.add("python")
    if (root / "Cargo.toml").exists():
        langs.add("rust")
    if (root / "go.mod").exists():
        langs.add("go")
    
    package_json = root / "package.json"
    if package_json.exists():
        langs.add("node")
    return langs

def resolve_target_python(ctx: TargetEnvContext) -> str:
    """
    優先從 target_venv 尋找 Python 直譯器，
    若無則 fallback 到 target_repo_root / .venv，最後 fallback 到 sys.executable。
    """
    if ctx.target_venv:
        # Mac/Linux
        python_bin = ctx.target_venv / "bin" / "python3"
        if not python_bin.exists():
            # Windows
            python_bin = ctx.target_venv / "Scripts" / "python.exe"
        if python_bin.exists():
            return str(python_bin)
        
        if (ctx.target_venv / "bin" / "python").exists():
            return str(ctx.target_venv / "bin" / "python")
        if ctx.target_venv.is_file() and os.access(ctx.target_venv, os.X_OK):
            return str(ctx.target_venv)

    python_bin = ctx.target_repo_root / ".venv" / "bin" / "python3"
    if not python_bin.exists():
        python_bin = ctx.target_repo_root / ".venv" / "Scripts" / "python.exe"
    if python_bin.exists():
        return str(python_bin)

    return sys.executable

def build_verify_commands(ctx: TargetEnvContext) -> list[str]:
    """根據 TargetEnvContext 自動偵測並構建驗證指令"""
    cmds = []
    langs = detect_project_language(ctx.target_repo_root)
    
    if "python" in langs:
        venv_python = resolve_target_python(ctx)
        cmds.append(f"{venv_python} -m pytest --tb=short -q")
        
    if "rust" in langs:
        cmds.append("cargo test --lib 2>&1")
        
    if "go" in langs:
        cmds.append("go test ./... 2>&1")
        
    if "node" in langs:
        package_json = ctx.target_repo_root / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
                if isinstance(scripts, dict) and scripts.get("test"):
                    cmds.append("npm test --silent 2>&1")
            except Exception as exc:
                logger.debug("package_json_parse_failed: %s", exc)
                
    return cmds

def _auto_detect_verify_commands(project_root: Path) -> List[str]:
    """根據專案語言自動推斷驗證指令 (Deprecated)"""
    ctx = TargetEnvContext(
        engine_root=project_root,
        target_repo_root=project_root,
        target_venv=None,
        run_dir=None
    )
    return build_verify_commands(ctx)
