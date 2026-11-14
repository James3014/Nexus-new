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
    "nexus/orchestrator/collaboration_realm.py",
    "nexus/orchestrator/governed_integration.py",
    "nexus/services/agy_reviewer_runtime.py",
    "nexus/services/external_intelligence_closure.py",
    "nexus/services/external_intelligence_automation.py",
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


PINNING_HELPERS = {"history_pinned_env", "hardened_git_env", "_git_no_replace_env"}


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


def _names_in(target):
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


# Keys worktree_manager sets after pinning; they only disable system/global config, so they
# cannot weaken the history pins. Any other GIT_* key (or a non-constant key) is tampering.
HARMLESS_GIT_KEYS = {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT"}


def _is_safe_item_key(key):
    if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
        return False
    upper = key.value.upper()
    return not upper.startswith("GIT_") or upper in HARMLESS_GIT_KEYS


def _env_name_is_tampered(name, scope):
    """True when the pinned-looking name is later changed in a way that could weaken the pins:
    item set/delete (only constant non-GIT_* keys are allowed), update/pop/setdefault/clear,
    annotated or augmented assignment, or a tuple/for/with rebinding."""
    for node in ast.walk(scope):
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if name in _names_in(node.target):
                return True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if name in _names_in(target.value) and not _is_safe_item_key(target.slice):
                        return True
                elif not isinstance(target, ast.Name) and name in _names_in(target):
                    return True
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if name in _names_in(target):
                    return True
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            if name in _names_in(node.target):
                return True
        elif isinstance(node, ast.NamedExpr):
            if name in _names_in(node.target):
                return True
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if (
                isinstance(owner, ast.Name)
                and owner.id == name
                and node.func.attr in {"update", "pop", "popitem", "setdefault", "clear"}
            ):
                return True
    return False


def _env_is_pinned(call, scope):
    """env= must be a history_pinned_env()/hardened_git_env() call, or a name that every
    plain assignment in the enclosing scope sets from one and that is never tampered with."""
    env = next((kw.value for kw in call.keywords if kw.arg == "env"), None)
    if env is None:
        return False
    if _is_pinning_call(env):
        return True
    if not isinstance(env, ast.Name):
        return False
    if _env_name_is_tampered(env.id, scope):
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
            if command == "diff" and any(
                isinstance(arg, ast.Constant) and arg.value in {"--cached", "--no-index"}
                for arg in node.args[0].elts
            ):
                command = None
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
        'def f():\n    e = history_pinned_env()\n    e["GIT_NO_REPLACE_OBJECTS"] = "0"\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e[k] = "0"\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e.update(GIT_GRAFT_FILE="x")\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e.pop("GIT_NO_REPLACE_OBJECTS")\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    del e["GIT_NO_REPLACE_OBJECTS"]\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e: dict = os.environ.copy()\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e |= {"GIT_GRAFT_FILE": "x"}\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e.setdefault("A", "1")\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
    ],
)
def test_guard_flags_unpinned_history_calls(source):
    assert unpinned_history_calls(source)


@pytest.mark.parametrize(
    "source",
    [
        'subprocess.run(["git", "merge-base", "a", "b"], env=history_pinned_env())',
        'subprocess.run(["git", "-c", "k=v", "rev-parse", "HEAD"], env=m().hardened_git_env(p))',
        'def f():\n    e = history_pinned_env(base)\n    e["GIT_CONFIG_NOSYSTEM"] = "1"\n    e["X"] = "1"\n    subprocess.run(["git", "diff"], env=e)',
        'subprocess.run(["git", "status"])',
        'subprocess.run(["git", "init"])',
    ],
)
def test_guard_accepts_pinned_or_non_history_calls(source):
    assert unpinned_history_calls(source) == []
