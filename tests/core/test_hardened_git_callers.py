"""History-reading subprocess git callers must pin repository-controlled history."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "nexus/orchestrator/worktree_manager.py",
    "nexus/orchestrator/self_hosted_task_service.py",
    "nexus/orchestrator/self_hosted_task_service_parts/reconcile_recovery.py",
    "nexus/orchestrator/self_hosted_task_service_parts/task_build.py",
    "nexus/orchestrator/self_hosted_task_service_parts/retry_helpers.py",
    "nexus/orchestrator/unified_mcp_gateway.py",
    "nexus/orchestrator/unified_mcp_gateway_parts/worker_candidate.py",
    "nexus/orchestrator/unified_mcp_gateway_parts/candidate_ops.py",
)
HISTORY_COMMANDS = {"merge-base", "rev-list", "diff", "log", "rev-parse", "cat-file", "show"}


def _git_subcommand(args):
    """The git subcommand of a literal argv list, skipping leading -c k=v / flags.

    Returns None when it is not a git call, "?" when it cannot be told statically."""
    if not args or not (isinstance(args[0], ast.Constant) and args[0].value == "git"):
        return None
    i = 1
    while i < len(args):
        arg = args[i]
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            return "?"
        if arg.value in {"-c", "-C"}:
            i += 2
        elif arg.value.startswith("-"):
            i += 1
        else:
            return arg.value
    return "?"


PINNING_HELPERS = {"history_pinned_env", "hardened_git_env"}


def _is_subprocess_call(node):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"run", "check_output", "Popen", "check_call", "call"}:
        return False
    owner = node.func.value
    return (isinstance(owner, ast.Name) and owner.id == "subprocess") or (
        isinstance(owner, ast.Attribute) and owner.attr == "subprocess"
    )


def _is_pinning_call(value):
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return name in PINNING_HELPERS


def _env_is_pinned(call, scope):
    """env= must be a history_pinned_env()/hardened_git_env() call, or a name that every
    assignment in the enclosing scope sets from one (item assignment is allowed)."""
    env = next((kw.value for kw in call.keywords if kw.arg == "env"), None)
    if env is None:
        return False
    if _is_pinning_call(env):
        return True
    if not isinstance(env, ast.Name):
        return False
    values = [
        node.value
        for node in ast.walk(scope)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == env.id for t in node.targets)
    ]
    return bool(values) and all(
        _is_pinning_call(v)
        or (
            isinstance(v, ast.Call)
            and getattr(v.func, "attr", "") == "copy"
            and _is_pinning_call(v.func.value)
        )
        for v in values
    )


def unpinned_history_calls(source, name="<src>"):
    tree = ast.parse(source, filename=name)
    offenders = []

    def visit(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = node
        if (
            _is_subprocess_call(node)
            and node.args
            and isinstance(node.args[0], (ast.List, ast.Tuple))
        ):
            command = _git_subcommand(node.args[0].elts)
            if command is not None and (command == "?" or command in HISTORY_COMMANDS):
                if not _env_is_pinned(node, scope):
                    offenders.append(f"{name}:{node.lineno}")
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, tree)
    return offenders


def test_history_reading_subprocess_git_calls_pass_env():
    offenders = []
    for name in FILES:
        source = (ROOT / name).read_text(encoding="utf-8")
        offenders += unpinned_history_calls(source, name)
    assert offenders == [], "history-reading git subprocesses without a pinned env: " + ", ".join(
        offenders
    )


@pytest.mark.parametrize(
    "source",
    [
        'subprocess.run(["git", "merge-base", "a", "b"])',
        'subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "merge-base", "a", "b"])',
        'x.subprocess.run(["git", "rev-parse", "HEAD"], cwd=c)',
        'subprocess.run(["git", *args], env=os.environ.copy())',
        'subprocess.run(["git", "diff"], env=os.environ.copy())',
        'subprocess.run(["git", "rev-list", "x"], env=env)',
        'def f():\n    env = dict(os.environ)\n    subprocess.run(["git", "log"], env=env)',
        'subprocess.check_output(["git", "show", "HEAD"], env={})',
    ],
)
def test_guard_flags_unpinned_history_calls(source):
    assert unpinned_history_calls(source)


@pytest.mark.parametrize(
    "source",
    [
        'subprocess.run(["git", "merge-base", "a", "b"], env=history_pinned_env())',
        'subprocess.run(["git", "-c", "k=v", "rev-parse", "HEAD"], env=m().hardened_git_env(p))',
        'def f():\n    e = history_pinned_env(base)\n    e["X"] = "1"\n    subprocess.run(["git", "diff"], env=e)',
        'subprocess.run(["git", "status"])',
        'subprocess.run(["git", "init"])',
    ],
)
def test_guard_accepts_pinned_or_non_history_calls(source):
    assert unpinned_history_calls(source) == []
