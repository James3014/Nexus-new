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
import tempfile
import json
from dataclasses import replace
from types import SimpleNamespace
from nexus.core.contained_write import drop_escaping_links
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
# Not copied into the disposable pregate workspace (same set World C skips).
_PREGATE_COPY_SKIPPED = (
    ".git", ".nexus", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__", "node_modules"
)
_PREGATE_COPY_IGNORED = shutil.ignore_patterns(*_PREGATE_COPY_SKIPPED)
# The live controller copies ~165 MB in ~2 s; a far larger root fails closed instead.
_PREGATE_COPY_MAX_BYTES = 1 << 30


def _relocate_token(token: str, source: Path, copy: Path) -> str:
    """Point an argument naming ``source`` (or a path under it) at the same path in ``copy``.

    ``-o=<path>``/``--opt=<path>`` are handled too, and paths that do not exist yet (outputs)
    move as well. Paths into a directory that is not copied (e.g. the root's ``.venv``) stay.
    """
    head, sep, value = token.partition("=") if token.startswith("-") and "=" in token else ("", "", token)
    for root in dict.fromkeys((str(source), str(source.resolve()))):
        if value == root or value.startswith(root + os.sep):
            rest = value[len(root):]
            if rest.lstrip(os.sep).split(os.sep, 1)[0] in _PREGATE_COPY_SKIPPED:
                return token
            return f"{head}{sep}{copy}{rest}"
    return token


def _build_pregate_request(
    cmd: str,
    cwd: Path,
    env_overlay: dict,
    timeout: float = 60.0,
    relocate_from: Optional[Path] = None,
):
    """Tokenize ``cmd`` WITHOUT a shell and build a governed CliWorkerRequest.

    The request goes through the same no-shell launcher, forbidden-subcommand
    denylist, GitHub credential stripping and isolated HOME as every other
    verifier/worker spawn.  Raises ValueError when the command needs a shell.
    With ``relocate_from``, arguments naming that root are re-pointed at ``cwd`` (its copy).
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
    if relocate_from is not None:
        executable = _relocate_token(executable, relocate_from, cwd)
        args = [_relocate_token(token, relocate_from, cwd) for token in args]
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
    *,
    isolate_workspace: bool = False,
) -> Tuple[bool, List[dict]]:
    """
    執行驗證指令列表，回傳 (all_passed, results)

    ``isolate_workspace=True`` runs the commands in a disposable copy of the root under the
    model-output OS sandbox (no network, writes only in the copy), so a caller's verifier can
    never change the root itself (#2967). Off macOS, or on macOS only when the operator set
    ``NEXUS_DISABLE_OS_SANDBOX=1``, there is no OS barrier and the commands run unconfined in
    the copy (``confinement: copy_only``): that stops cwd-relative writes, not a command that
    writes absolute paths, the network or ``$HOME``. Every other sandbox error, a failed copy
    or a copy over the size cap fails closed.
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
    
    if isolate_workspace:
        try:
            with tempfile.TemporaryDirectory(prefix="nexus-pregate-", ignore_cleanup_errors=True) as scratch:
                work_dir = Path(scratch).resolve()
                shutil.copytree(
                    target_repo_root,
                    work_dir,
                    symlinks=True,
                    ignore=_PREGATE_COPY_IGNORED,
                    copy_function=_bounded_copy([_PREGATE_COPY_MAX_BYTES]),
                    dirs_exist_ok=True,
                )
                # Links stay links in the copy; one that leaves it would let a relative
                # write in copy_only mode land outside the copy (#3130).
                drop_escaping_links(work_dir)
                env["PYTHONPATH"] = str(work_dir)
                return _run_pregate_commands(
                    commands, work_dir, env, timeout_per_cmd, confined=True, source_root=target_repo_root
                )
        except _CopyCapExceeded:
            return False, _fail_closed_results(commands, "pregate workspace over the copy size cap")
        except (OSError, shutil.Error) as exc:
            return False, _fail_closed_results(commands, f"pregate workspace copy failed: {exc}")
    return _run_pregate_commands(commands, target_repo_root, env, timeout_per_cmd, confined=False)


class _CopyCapExceeded(Exception):
    """Not an OSError, so ``copytree`` stops at the first file over the cap instead of
    collecting one error per remaining file."""


def _bounded_copy(budget: List[int]):
    def copy(src, dst, *, follow_symlinks=True):
        budget[0] -= os.lstat(src).st_size
        if budget[0] < 0:
            raise _CopyCapExceeded()
        return shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

    return copy


def _copy_only_allowed() -> bool:
    """Unconfined copy runs only where no barrier exists, or when the operator turned the
    model sandbox off on purpose; a broken ``sandbox-exec`` on macOS fails closed."""

    return sys.platform != "darwin" or os.environ.get("NEXUS_DISABLE_OS_SANDBOX") == "1"


def _fail_closed_results(commands: List[str], reason: str) -> List[dict]:
    logger.warning("❌ CLI Pre-Gate REFUSED: %s", reason[:500])
    return [{"cmd": cmd, "exit_code": -1, "passed": False, "stderr_tail": reason[-500:]} for cmd in commands]


def _run_confined_worker(request):
    """Run ``request`` in its cwd under the model-output sandbox (#2967).

    Reads are widened only for the resolved interpreter and absolute file arguments, as for
    the local_heal verifiers; the environment is the sandbox's private one plus PATH and
    PYTHONPATH. Raises SandboxError when there is no OS barrier.
    """
    from nexus.engine.model_output_sandbox import (
        SANDBOX_EXEC,
        argument_file_roots,
        interpreter_readable_roots,
        model_sandbox,
    )
    from nexus.executors.cli_worker import run_cli_worker

    readable = (*interpreter_readable_roots(request.executable), *argument_file_roots(request.command))
    with model_sandbox(request.cwd, readable=readable) as (prefix, sandbox_env):
        if len(prefix) != 3 or prefix[:2] != [SANDBOX_EXEC, "-p"]:
            raise ValueError("unexpected model sandbox prefix")
        env = {**sandbox_env, **{key: request.env[key] for key in ("PATH", "PYTHONPATH")}}
        return run_cli_worker(
            replace(
                request,
                env=env,
                exact_env=True,
                seatbelt_profile=prefix[2],
                sweep_descendants_on_exit=True,
                sweep_roots=(request.cwd,),
            )
        )


def _run_pregate_commands(
    commands: List[str],
    cwd: Path,
    env: dict,
    timeout_per_cmd: int,
    *,
    confined: bool,
    source_root: Optional[Path] = None,
) -> Tuple[bool, List[dict]]:
    from nexus.engine.model_output_sandbox import SandboxError

    results = []
    all_passed = True
    
    for cmd in commands:
        try:
            logger.info("🧪 [Pre-Gate] 執行驗證: %s", cmd)
            from nexus.executors.cli_worker import CliWorkerStatus, run_cli_worker

            try:
                request = _build_pregate_request(cmd, cwd, env, timeout_per_cmd, relocate_from=source_root)
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
            confinement = None
            if confined:
                try:
                    worker = _run_confined_worker(request)
                    confinement = "os_sandbox"
                except SandboxError as exc:
                    if str(exc) != "no_os_barrier" or not _copy_only_allowed():
                        results.extend(_fail_closed_results([cmd], f"pregate sandbox unavailable: {exc}"))
                        all_passed = False
                        continue
                    # No OS barrier on this host (Linux, or the operator's kill switch): run in
                    # the disposable copy, never in the root; labelled so receipts show it.
                    worker = run_cli_worker(
                        replace(request, sweep_descendants_on_exit=True, sweep_roots=(request.cwd,))
                    )
                    confinement = "copy_only"
                except ValueError as exc:
                    results.extend(_fail_closed_results([cmd], f"pregate sandbox unavailable: {exc}"))
                    all_passed = False
                    continue
            else:
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
                **({"confinement": confinement} if confinement else {}),
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
