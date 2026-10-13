import shlex
import subprocess
import hashlib
import time
import sys
import os
from pathlib import Path
from typing import Dict, List, Any

_SHELL_METACHARS = set(";|&$`<>")

# Only verification commands may be replayed. Everything else is recorded as
# REJECTED and never executed (an evidence file must not run arbitrary binaries).
_PYTHON_BINARIES = frozenset({"python", "python3"})
# Options that load arbitrary code/config or mutate the tree are never replayed.
_DENIED_PYTEST_OPTS = frozenset({"-p", "-c", "-o", "--override-ini", "--confcutdir", "--rootdir"})
_DENIED_RUFF_OPTS = frozenset(
    {"--fix", "--unsafe-fixes", "--add-noqa", "--config", "--output-file", "--watch", "--isolated"}
)
REPLAY_TIMEOUT_SECONDS = 60


def _allowlist_reject(binary: str) -> ValueError:
    return ValueError(f"command_not_allowlisted:{binary}")


def _check_allowlisted(argv: List[str]) -> None:
    """Raise ValueError('command_not_allowlisted:<binary>') unless argv is an allowed verification command."""
    head = argv[0]
    rest = argv[1:]
    if head == "uv":
        if not rest or rest[0] != "run":
            raise _allowlist_reject("uv")
        head, rest = (rest[1] if len(rest) > 1 else "uv"), rest[2:]
    if head == "pytest":
        denied, tool_args = _DENIED_PYTEST_OPTS, rest
    elif head in _PYTHON_BINARIES:
        if rest[:2] != ["-m", "pytest"]:
            raise _allowlist_reject(head)
        denied, tool_args = _DENIED_PYTEST_OPTS, rest[2:]
    elif head == "ruff":
        if rest[:1] != ["check"]:
            raise _allowlist_reject("ruff")
        denied, tool_args = _DENIED_RUFF_OPTS, rest[1:]
    else:
        raise _allowlist_reject(head)
    for arg in tool_args:
        name = arg.split("=", 1)[0]
        if name in denied or (len(arg) > 2 and arg[:2] in {"-p", "-c", "-o"} and not arg.startswith("--") and head != "ruff"):
            raise ValueError(f"command_option_not_allowed:{name}")
        if ".." in Path(arg).parts:
            raise ValueError("command_path_escape: '..' path segments not allowed")


def _parse_command(cmd: Any) -> List[str]:
    """Parse an evidence command into an allowlisted argv list; raise ValueError if unsafe."""
    if not isinstance(cmd, str) or not cmd.strip():
        raise ValueError("invalid_command: command must be a non-empty string")
    bad = sorted(ch for ch in _SHELL_METACHARS if ch in cmd)
    if bad:
        raise ValueError(f"unsafe_command: shell metacharacters not allowed: {''.join(bad)}")
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        raise ValueError(f"invalid_command: {exc}") from exc
    if not argv:
        raise ValueError("invalid_command: command must be a non-empty string")
    _check_allowlisted(argv)
    return argv


class ReplayRunner:
    """
    Stage 2: Physical Replay Runner.
    執行實體命令對質，不接受 Agent 的口頭自述。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        
    def run_replay(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        重跑 evidence bundle 中所列的 test_artifacts。
        """
        replay_results = []
        overall_passed = True
        rejected = 0
        notes = 0
        executed = 0

        test_artifacts = bundle.get("test_artifacts", [])
        if not test_artifacts:
            return {
                "status": "SKIPPED",
                "reason": "no_test_artifacts_to_replay",
                "passed": True,
                "replay_count": 0
            }
        if not isinstance(test_artifacts, list):
            test_artifacts = [test_artifacts]

        for spec in test_artifacts:
            # Strings (e.g. "claims_count=7") and dicts without a command are evidence
            # notes: recorded, never executed, never counted as a passed replay.
            if not isinstance(spec, dict) or "command" not in spec:
                notes += 1
                replay_results.append({
                    "artifact": spec if isinstance(spec, str) else repr(spec),
                    "status": "NOT_REPLAYABLE",
                    "replayable": False,
                    "executed": False,
                    "passed": False
                })
                continue
            cmd = spec.get("command")
            expected_rc = spec.get("exit_code", 0)
            expected_hash = spec.get("output_hash")

            start_time = time.time()
            try:
                argv = _parse_command(cmd)
            except ValueError as e:
                overall_passed = False
                rejected += 1
                replay_results.append({
                    "command": cmd if isinstance(cmd, str) else repr(cmd),
                    "status": "REJECTED",
                    "error": str(e),
                    "reason": str(e),
                    "executed": False,
                    "passed": False
                })
                continue
            try:
                result = subprocess.run(
                    argv, cwd=self.project_root,
                    capture_output=True, text=True, timeout=REPLAY_TIMEOUT_SECONDS
                )
                executed += 1
                duration = int((time.time() - start_time) * 1000)
                
                # 計算輸出 hash (簡化版：只針對 stdout)
                actual_hash = hashlib.sha256(result.stdout.encode()).hexdigest()
                
                match_rc = (result.returncode == expected_rc)
                match_hash = (actual_hash == expected_hash) if expected_hash else True
                
                item_passed = match_rc and match_hash
                if not item_passed:
                    overall_passed = False
                    
                replay_results.append({
                    "command": cmd,
                    "status": "EXECUTED",
                    "executed": True,
                    "actual_exit_code": result.returncode,
                    "expected_exit_code": expected_rc,
                    "actual_hash": actual_hash,
                    "expected_hash": expected_hash,
                    "match_rc": match_rc,
                    "match_hash": match_hash,
                    "duration_ms": duration,
                    "passed": item_passed
                })
            except Exception as e:
                overall_passed = False
                replay_results.append({
                    "command": cmd,
                    "status": "ERROR",
                    "executed": False,
                    "error": str(e),
                    "passed": False
                })

        if rejected:
            status = "REJECTED"
        elif not overall_passed:
            status = "FAILED"
        elif executed == 0:
            # Nothing was actually replayed: do not claim COMPLETED.
            status = "NOT_REPLAYED"
        else:
            status = "COMPLETED"
        return {
            "status": status,
            "passed": overall_passed,
            "replay_results": replay_results,
            "replay_count": executed,
            "rejected_count": rejected,
            "non_replayable_count": notes,
            "env_info": {
                "python": sys.version,
                "platform": sys.platform,
                "cwd": os.getcwd()
            }
        }
