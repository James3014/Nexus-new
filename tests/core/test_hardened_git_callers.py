"""History-reading subprocess git callers must pin repository-controlled history."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "nexus/orchestrator/worktree_manager.py",
    "nexus/orchestrator/self_hosted_task_service.py",
    "nexus/orchestrator/self_hosted_task_service_parts/reconcile_recovery.py",
    "nexus/orchestrator/self_hosted_task_service_parts/task_build.py",
    "nexus/orchestrator/self_hosted_task_service_parts/retry_helpers.py",
    "nexus/orchestrator/unified_mcp_gateway.py",
    "nexus/orchestrator/unified_mcp_gateway_parts/worker_candidate.py",
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


def _is_subprocess_call(node):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"run", "check_output", "Popen", "check_call", "call"}:
        return False
    owner = node.func.value
    return (isinstance(owner, ast.Name) and owner.id == "subprocess") or (
        isinstance(owner, ast.Attribute) and owner.attr == "subprocess"
    )


def test_history_reading_subprocess_git_calls_pass_env():
    offenders = []
    for name in FILES:
        source = (ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if not _is_subprocess_call(node):
                continue
            if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)):
                continue
            command = _git_subcommand(node.args[0].elts)
            if command is None or (command != "?" and command not in HISTORY_COMMANDS):
                continue
            if not any(keyword.arg == "env" for keyword in node.keywords):
                offenders.append(f"{name}:{node.lineno}")
    assert offenders == [], "history-reading git subprocesses without env: " + ", ".join(offenders)


def test_guard_sees_leading_config_flags_and_plain_subprocess_calls():
    tree = ast.parse('subprocess.run(["git", "-c", "a=b", "merge-base", "x"])')
    call = tree.body[0].value
    assert _is_subprocess_call(call)
    assert _git_subcommand(call.args[0].elts) == "merge-base"
