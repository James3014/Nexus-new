import shlex
import subprocess
import hashlib
import time
import sys
import os
from pathlib import Path
from typing import Dict, List, Any

_SHELL_METACHARS = set(";|&$`<>") | {"\n", "\r", "\x00"}

# Only verification commands may be replayed. Everything else is recorded as
# REJECTED and never executed (an evidence file must not run arbitrary binaries).
# Options are ALLOWLISTED (#2634): pytest and ruff options that write files
# (--basetemp, --junitxml, --log-file, --debug, --fix ...), load code or config
# (-p <plugin>, -c/--config-file, -o, -W, --pyargs ...) or move the root are
# refused, including inside clustered short flags (-vc, -qo, -qp).  Positional
# paths must resolve (realpath) inside the project root.
_PYTHON_BINARIES = frozenset({"python", "python3"})
REPLAY_TIMEOUT_SECONDS = 60

# pytest short flags without a value, and short flags whose value follows
# (attached or as the next argument), with a validator for the value.
_PYTEST_SHORT_FLAGS = frozenset("qvxsl")
_PYTEST_LONG_FLAGS = frozenset({
    "--quiet", "--verbose", "--exitfirst", "--showlocals", "--no-header",
    "--no-summary", "--lf", "--last-failed", "--ff", "--failed-first", "--co",
    "--collect-only", "--version", "--strict-markers", "--sw", "--stepwise",
    "--new-first", "--nf", "--setup-show", "--disable-warnings",
})
_TB_STYLES = frozenset({"auto", "long", "short", "line", "native", "no"})
_REPORT_CHARS = frozenset("fEsxXpPaAN")


def _digits(value: str) -> bool:
    return value.isdigit()


def _expression(value: str) -> bool:
    # -k / -m expressions are parsed by pytest's own matcher, never eval'd.
    return bool(value) and "\x00" not in value


def _no_plugin(value: str) -> bool:
    # Only disabling a plugin is allowed (-p no:cacheprovider); loading one is code.
    name = value[3:] if value.startswith("no:") else ""
    return bool(name) and all(ch.isalnum() or ch in "_.-" for ch in name)


_PYTEST_SHORT_VALUE_FLAGS = {
    "k": _expression,
    "m": _expression,
    "r": lambda v: bool(v) and set(v) <= _REPORT_CHARS,
    "p": _no_plugin,
}
_PYTEST_LONG_VALUE_FLAGS = {
    "--tb": lambda v: v in _TB_STYLES,
    "--maxfail": _digits,
    "--durations": _digits,
    "--capture": lambda v: v in {"no", "sys", "fd", "tee-sys"},
    "--color": lambda v: v in {"yes", "no", "auto"},
    "--deselect": None,  # a node id: path-checked below
}
_RUFF_LONG_FLAGS = frozenset({
    "--quiet", "--no-cache", "--statistics", "--exit-zero", "--show-fixes",
    "--preview", "--diff", "--no-fix",
})
_RUFF_SHORT_FLAGS = frozenset("q")
_RUFF_LONG_VALUE_FLAGS = {
    "--select": None, "--ignore": None, "--extend-select": None,
    "--extend-ignore": None, "--output-format": None, "--target-version": None,
}


def _allowlist_reject(binary: str) -> ValueError:
    return ValueError(f"command_not_allowlisted:{binary}")


def _option_reject(name: str) -> ValueError:
    return ValueError(f"command_option_not_allowed:{name}")


def _check_path(arg: str, project_root: Path) -> None:
    """A positional test path / node id must resolve inside the project root."""
    path_part = arg.split("::", 1)[0]
    if not path_part:
        raise ValueError("command_path_escape: empty path")
    if ".." in Path(path_part).parts:
        raise ValueError("command_path_escape: '..' path segments not allowed")
    root = os.path.realpath(project_root)
    target = os.path.realpath(os.path.join(root, path_part))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("command_path_escape: path resolves outside the project root")


def _check_tool_args(
    args: List[str],
    project_root: Path,
    short_flags: frozenset,
    short_value_flags: Dict[str, Any],
    long_flags: frozenset,
    long_value_flags: Dict[str, Any],
) -> None:
    for arg in args:
        # pytest (argparse fromfile_prefix_chars="@") expands "@file" into more
        # options, so a file holding --basetemp=<dir> would bypass this list.
        # Refuse "@" at the start of any token or option value (#2634, B4).
        if arg.startswith("@") or "=@" in arg:
            raise _option_reject("@file")
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--" or not arg.startswith("-") or arg == "-":
            if arg in {"--", "-"}:
                raise _option_reject(arg)
            _check_path(arg, project_root)
            continue
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in long_flags and not eq:
                continue
            if name not in long_value_flags:
                raise _option_reject(name)
            if not eq:
                if index >= len(args):
                    raise _option_reject(name)
                value = args[index]
                index += 1
            validator = long_value_flags[name]
            if validator is None:
                if name == "--deselect":
                    _check_path(value, project_root)
                elif not value or value.startswith("-"):
                    raise _option_reject(name)
            elif not validator(value):
                raise _option_reject(name)
            continue
        # Short flags, possibly clustered (-qvx, -ra, -kexpr): validate every letter.
        cluster = arg[1:]
        for pos, ch in enumerate(cluster):
            if ch in short_flags:
                continue
            if ch in short_value_flags:
                value = cluster[pos + 1:]
                if not value:
                    if index >= len(args):
                        raise _option_reject(f"-{ch}")
                    value = args[index]
                    index += 1
                if value.startswith("@") or not short_value_flags[ch](value):
                    raise _option_reject(f"-{ch}")
                break
            raise _option_reject(f"-{ch}")


def _check_allowlisted(argv: List[str], project_root: Path) -> None:
    """Raise ValueError unless argv is an allowed verification command with allowed options."""
    head = argv[0]
    rest = argv[1:]
    if head == "uv":
        if not rest or rest[0] != "run":
            raise _allowlist_reject("uv")
        head, rest = (rest[1] if len(rest) > 1 else "uv"), rest[2:]
    if head == "pytest":
        tool_args = rest
    elif head in _PYTHON_BINARIES:
        if rest[:2] != ["-m", "pytest"]:
            raise _allowlist_reject(head)
        tool_args = rest[2:]
    elif head == "ruff":
        if rest[:1] != ["check"]:
            raise _allowlist_reject("ruff")
        _check_tool_args(
            rest[1:], project_root, _RUFF_SHORT_FLAGS, {}, _RUFF_LONG_FLAGS, _RUFF_LONG_VALUE_FLAGS
        )
        return
    else:
        raise _allowlist_reject(head)
    check_pytest_args(tool_args, project_root)


def check_pytest_args(args: List[str], project_root: Path) -> None:
    """Shared pytest option allowlist (replay runner and evidence verifier, #2634)."""
    _check_tool_args(
        list(args),
        Path(project_root),
        _PYTEST_SHORT_FLAGS,
        _PYTEST_SHORT_VALUE_FLAGS,
        _PYTEST_LONG_FLAGS,
        _PYTEST_LONG_VALUE_FLAGS,
    )


# pytest options that make the run execute no tests (#2685).
_PYTEST_NON_RUNNING_FLAGS = frozenset({
    "--version", "--co", "--collect-only", "--help", "--fixtures", "--funcargs",
    "--fixtures-per-test", "--markers", "--setup-plan",
})
# Short forms (-V version, -h help), also inside clusters such as -qV.  Scanning a cluster
# stops at a flag whose value follows (-k/-m/-r/-p), e.g. "-kVh" is "-k Vh".
_PYTEST_NON_RUNNING_SHORT = frozenset("Vh")
_PYTEST_SHORT_VALUE_LETTERS = frozenset(_PYTEST_SHORT_VALUE_FLAGS)


def pytest_arg_is_non_running(arg: str) -> bool:
    """True when this single pytest option makes the run execute no tests."""
    if arg.startswith("--"):
        return arg.partition("=")[0] in _PYTEST_NON_RUNNING_FLAGS
    if not arg.startswith("-") or arg == "-":
        return False
    for ch in arg[1:]:
        if ch in _PYTEST_NON_RUNNING_SHORT:
            return True
        if ch in _PYTEST_SHORT_VALUE_LETTERS:
            return False
    return False


def command_runs_tests(argv: List[str]) -> bool:
    """True when an allowlisted argv really runs pytest tests.

    ``ruff check`` and pytest with ``--version`` / ``--collect-only`` replay fine but prove
    nothing about tests passing.
    """
    head, rest = argv[0], argv[1:]
    if head == "uv" and rest[:1] == ["run"]:
        head, rest = (rest[1] if len(rest) > 1 else "uv"), rest[2:]
    if head in _PYTHON_BINARIES and rest[:2] == ["-m", "pytest"]:
        rest = rest[2:]
    elif head != "pytest":
        return False
    return not any(pytest_arg_is_non_running(arg) for arg in rest)


def split_command(cmd: Any) -> List[str]:
    """shlex-split a command string after refusing shell metacharacters; raise ValueError."""
    if not isinstance(cmd, str) or not cmd.strip():
        raise ValueError("invalid_command: command must be a non-empty string")
    bad = sorted(ch for ch in _SHELL_METACHARS if ch in cmd)
    if bad:
        raise ValueError(f"unsafe_command: shell metacharacters not allowed: {''.join(bad)!r}")
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        raise ValueError(f"invalid_command: {exc}") from exc
    if not argv:
        raise ValueError("invalid_command: command must be a non-empty string")
    return argv


def _parse_command(cmd: Any, project_root: Any = None) -> List[str]:
    """Parse an evidence command into an allowlisted argv list; raise ValueError if unsafe."""
    argv = split_command(cmd)
    _check_allowlisted(argv, Path(project_root) if project_root is not None else Path.cwd())
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
        test_running = 0

        test_artifacts = bundle.get("test_artifacts", [])
        if not test_artifacts:
            # Nothing to replay is not a success (#2685): passed is False and the verdict
            # is UNVERIFIED.  Callers that treat missing coverage as advisory read status.
            return {
                "status": "SKIPPED",
                "verdict": "UNVERIFIED",
                "reason": "no_test_artifacts_to_replay",
                "passed": False,
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
            # ``exit_code`` is what the receipt RECORDED.  There is no way to declare a
            # non-zero exit as the intended outcome: the agent writes the receipt (#2685).
            expected_rc = spec.get("exit_code", 0)
            expected_hash = spec.get("output_hash")

            start_time = time.time()
            try:
                argv = _parse_command(cmd, self.project_root)
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
                
                actual_rc = result.returncode
                match_rc = (actual_rc == expected_rc)
                # A recorded non-zero exit reproduced honestly is still a failing
                # verification, never a pass (#2685).
                exit_ok = actual_rc == 0
                runs_tests = command_runs_tests(argv)
                match_hash = (actual_hash == expected_hash) if expected_hash else True

                item_passed = match_rc and exit_ok and match_hash
                if item_passed and runs_tests:
                    test_running += 1
                if not item_passed:
                    overall_passed = False
                    
                replay_results.append({
                    "command": cmd,
                    "status": "EXECUTED",
                    "executed": True,
                    "actual_exit_code": result.returncode,
                    "expected_exit_code": expected_rc,
                    "exit_ok": exit_ok,
                    "runs_tests": runs_tests,
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

        verdict = None
        if rejected:
            status = "REJECTED"
        elif not overall_passed:
            status = "FAILED"
        elif executed == 0:
            # Nothing was actually replayed: do not claim COMPLETED, and never passed (#2685).
            status = "NOT_REPLAYED"
            verdict = "UNVERIFIED"
            overall_passed = False
        else:
            status = "COMPLETED"
        report: Dict[str, Any] = {
            "status": status,
            "passed": overall_passed,
            "replay_results": replay_results,
            "replay_count": executed,
            # Replayed commands that really run tests (not --version / --collect-only / ruff).
            "test_running_count": test_running,
            "rejected_count": rejected,
            "non_replayable_count": notes,
            "env_info": {
                "python": sys.version,
                "platform": sys.platform,
                "cwd": os.getcwd()
            }
        }
        if verdict:
            report["verdict"] = verdict
        return report
