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


def test_history_reading_subprocess_git_calls_pass_env():
    offenders = []
    for name in FILES:
        source = (ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"run", "check_output", "Popen"}:
                continue
            if (
                not isinstance(node.func.value, ast.Attribute)
                or node.func.value.attr != "subprocess"
            ):
                continue
            if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)):
                continue
            args = node.args[0].elts
            if len(args) < 2 or not all(isinstance(arg, ast.Constant) for arg in args[:2]):
                continue
            if args[0].value != "git" or args[1].value not in HISTORY_COMMANDS:
                continue
            if not any(keyword.arg == "env" for keyword in node.keywords):
                offenders.append(f"{name}:{node.lineno}")
    assert offenders == [], "history-reading git subprocesses without env: " + ", ".join(offenders)
