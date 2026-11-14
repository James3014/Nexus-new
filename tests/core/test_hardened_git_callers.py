"""History-reading subprocess git callers must pin repository-controlled history."""

import ast
import importlib.util
import os
import subprocess
import sys
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
    "scripts/ops/verify_report_claims.py",
    "scripts/ops/trusted_deletion_anchor.py",
    "scripts/ops/trusted_dependency_contract.py",
    "scripts/ops/mcp_gateway_durable.py",
    "scripts/ops/pr_preflight.py",
    "scripts/ops/sibling_bindings_check.py",
    "scripts/ops/check_gateway_source_drift.py",
    "scripts/ops/task_authority_freshness_check.py",
    "scripts/ops/closeout_guard.py",
    "scripts/ops/break_glass_recovery.py",
    "scripts/governance/livefail_rollback.py",
    "nexus/delivery/evidence_verifier.py",
    "nexus/engine/phases/audit.py",
    "nexus/engine/pipeline_repair.py",
    "nexus/engine/repair/audit_evaluator.py",
    "nexus/engine/planner_graph.py",
)
HISTORY_COMMANDS = {"merge-base", "rev-list", "diff", "log", "rev-parse", "cat-file", "show"}
# This call is the shared subprocess boundary: its `config` branch deliberately retains
# env-injected config for the merge-driver audit; every history command uses `run_env`.
GUARD_ALLOWLIST = {
    "nexus/orchestrator/governed_integration.py:199": "config subcommand keeps injected config visible; history subcommands use run_env",
}


@pytest.mark.parametrize(
    "path,helper",
    [
        ("scripts/ops/closeout_guard.py", "_history_pinned_env"),
        ("scripts/ops/task_authority_freshness_check.py", "_history_pinned_env"),
        ("scripts/ops/break_glass_recovery.py", "_history_pinned_env"),
        ("scripts/governance/livefail_rollback.py", "_history_pinned_env"),
        ("scripts/ops/check_gateway_source_drift.py", "_history_pinned_env"),
        ("scripts/ops/sibling_bindings_check.py", "_history_pinned_env"),
        ("scripts/ops/pr_preflight.py", "_history_pinned_env"),
        ("scripts/ops/trusted_deletion_anchor.py", "_anchor_git_env"),
        ("scripts/ops/mcp_gateway_durable.py", "_history_pinned_env"),
    ],
)
def test_script_local_history_env_helpers_pin_real_git(path, helper, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("script_helper_under_test", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setenv("GIT_GRAFT_FILE", "/hostile-graft")
    monkeypatch.setenv("GIT_NO_REPLACE_OBJECTS", "0")
    env = getattr(module, helper)()
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_GRAFT_FILE"] == os.devnull
    assert (
        subprocess.check_output(
            ["git", "config", "--get", "core.commitGraph"], cwd=tmp_path, env=env, text=True
        ).strip()
        == "false"
    )


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


PINNING_HELPERS = {
    "history_pinned_env",
    "hardened_git_env",
    "_git_no_replace_env",
    "_history_pinned_env",
    "_anchor_git_env",
}


def _is_subprocess_call(node, subprocess_aliases, run_aliases):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in run_aliases
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"run", "check_output", "Popen", "check_call", "call"}:
        return False
    owner = node.func.value
    return (isinstance(owner, ast.Name) and owner.id in subprocess_aliases) or (
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
    aliases = {name}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(scope):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in aliases:
                        aliases.add(target.id)
                        changed = True
    for node in ast.walk(scope):
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if _names_in(node.target) & aliases:
                return True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if _names_in(target.value) & aliases and not _is_safe_item_key(target.slice):
                        return True
                elif not isinstance(target, ast.Name) and _names_in(target) & aliases:
                    return True
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if _names_in(target) & aliases:
                    return True
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            if _names_in(node.target) & aliases:
                return True
        elif isinstance(node, ast.NamedExpr):
            if _names_in(node.target) & aliases:
                return True
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if (
                isinstance(owner, ast.Name)
                and owner.id in aliases
                and node.func.attr
                in {"update", "pop", "popitem", "setdefault", "clear", "__setitem__"}
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
    subprocess_aliases = {"subprocess"}
    run_aliases = set()
    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            for alias in item.names:
                if alias.name == "subprocess":
                    subprocess_aliases.add(alias.asname or "subprocess")
        elif isinstance(item, ast.ImportFrom) and item.module == "subprocess":
            for alias in item.names:
                if alias.name in {"run", "check_output", "Popen", "check_call", "call"}:
                    run_aliases.add(alias.asname or alias.name)

    def argv_command(argv, scope):
        if isinstance(argv, ast.Name):
            assigned = [
                node.value
                for node in ast.walk(scope)
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == argv.id for target in node.targets
                )
            ]
            if not assigned:
                return None
            values = [argv_command(value, scope) for value in assigned]
            return "?" if any(value in {"?", *HISTORY_COMMANDS} for value in values) else None
        if isinstance(argv, ast.BinOp) and isinstance(argv.op, ast.Add):
            left = argv.left
            if (
                isinstance(left, (ast.List, ast.Tuple))
                and left.elts
                and isinstance(left.elts[0], ast.Constant)
                and left.elts[0].value == "git"
            ):
                return "?"
            return None
        if not isinstance(argv, (ast.List, ast.Tuple)):
            return None
        if argv.elts and isinstance(argv.elts[0], ast.Starred):
            if any(isinstance(item, ast.Constant) and item.value == "--help" for item in argv.elts):
                return None
            return "?"
        if (
            not argv.elts
            or not isinstance(argv.elts[0], ast.Constant)
            or argv.elts[0].value != "git"
        ):
            return None
        return _git_subcommand(argv.elts)

    def visit(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = node
        if _is_subprocess_call(node, subprocess_aliases, run_aliases) and node.args:
            argv = node.args[0]
            command = argv_command(argv, scope)
            if command == "diff" and any(
                isinstance(arg, ast.Constant) and arg.value in {"--cached", "--no-index"}
                for arg in (argv.elts if isinstance(argv, (ast.List, ast.Tuple)) else [])
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
        offenders += [
            offender
            for offender in unpinned_history_calls(source, name)
            if offender not in GUARD_ALLOWLIST
        ]
    assert offenders == [], "history-reading git subprocesses without a pinned env: " + ", ".join(
        offenders
    )


def _assert_captured_git_is_pinned(argv, env, *, cli_pins=()):
    protected = {"core.commitgraph", "core.usereplacerefs", "core.graftfile"}
    expected_pins = {
        ("core.commitgraph", "false"),
        ("core.usereplacerefs", "false"),
        ("core.graftfile", os.devnull.lower()),
    }
    for index, arg in enumerate(argv):
        setting = None
        if arg == "-c" and index + 1 < len(argv):
            setting = argv[index + 1]
        elif arg.startswith("-c") and len(arg) > 2:
            setting = arg[2:]
        elif arg.startswith("--config-env="):
            setting = arg[len("--config-env=") :]
        elif arg == "--config-env" and index + 1 < len(argv):
            setting = argv[index + 1]
        if setting and setting.split("=", 1)[0].lower() in protected:
            key, _, value = setting.partition("=")
            if (key.lower(), value.lower()) not in expected_pins | set(cli_pins):
                pytest.fail(f"protected caller history config remained in argv: {argv!r}")
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_GRAFT_FILE"]
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "core.commitGraph"
    assert env["GIT_CONFIG_VALUE_0"] == "false"


def test_worktree_manager_run_git_removes_caller_history_config(tmp_path, monkeypatch):
    import subprocess

    from nexus.orchestrator import worktree_manager as wm

    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(argv=argv, env=kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, "ok\n", "")

    monkeypatch.setattr(wm.subprocess, "run", fake_run)
    manager = wm.WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=False)
    manager._run_git(
        [
            "-c",
            "core.commitGraph=true",
            "-ccore.useReplaceRefs=true",
            "--config-env=core.graftFile=EVIL",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "test.setting=kept",
            "rev-list",
            "HEAD",
        ],
        cwd=tmp_path,
    )
    _assert_captured_git_is_pinned(captured["argv"], captured["env"])
    assert all(
        value in captured["argv"]
        for value in (
            "test.setting=kept",
            "user.name=Test",
            "user.email=test@example.invalid",
            "core.fsmonitor=false",
        )
    )


def test_unified_gateway_git_removes_caller_history_config(tmp_path, monkeypatch):
    import subprocess

    from nexus.orchestrator import unified_mcp_gateway as gateway

    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(argv=argv, env=kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, "ok\n", "")

    monkeypatch.setattr(gateway, "CANONICAL_SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(gateway.subprocess, "run", fake_run)
    gateway._git(
        "-c",
        "core.commitGraph=true",
        "-c",
        "core.useReplaceRefs=true",
        "--config-env",
        "core.graftFile=EVIL",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "test.setting=kept",
        "rev-list",
        "HEAD",
    )
    _assert_captured_git_is_pinned(captured["argv"], captured["env"])
    assert all(
        value in captured["argv"]
        for value in ("test.setting=kept", "user.name=Test", "user.email=test@example.invalid")
    )


def test_mcp_gateway_durable_git_wrappers_remove_caller_history_config(tmp_path, monkeypatch):
    import subprocess

    from scripts.ops import mcp_gateway_durable as gateway

    captured = []

    def fake_check_output(argv, **kwargs):
        captured.append((argv, kwargs["env"]))
        return "ok\n"

    def fake_run(argv, **kwargs):
        captured.append((argv, kwargs["env"]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(gateway.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(gateway.subprocess, "run", fake_run)
    gateway._git(
        tmp_path,
        "-c",
        "core.commitGraph=true",
        "-ccore.useReplaceRefs=true",
        "--config-env=core.graftFile=EVIL",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "test.setting=kept",
        "rev-list",
        "HEAD",
    )
    assert gateway._is_ancestor(tmp_path, "a" * 40, "b" * 40)
    assert len(captured) == 2
    for argv, env in captured[:1]:
        _assert_captured_git_is_pinned(
            argv, env, cli_pins={("core.commitgraph", "false"), ("core.usereplacerefs", "false")}
        )
        assert all(
            value in argv
            for value in ("test.setting=kept", "user.name=Test", "user.email=test@example.invalid")
        )
    _assert_captured_git_is_pinned(
        captured[1][0],
        captured[1][1],
        cli_pins={("core.commitgraph", "false"), ("core.usereplacerefs", "false")},
    )


@pytest.mark.parametrize("wrapper", ["worktree", "unified", "durable"])
@pytest.mark.parametrize(
    "form", ["pair", "upper", "joined", "gitdir", "branch", "env_equal", "env_pair"]
)
def test_git_wrappers_reject_include_history_config(wrapper, form, tmp_path, monkeypatch):
    from nexus.orchestrator import unified_mcp_gateway as unified
    from nexus.orchestrator import worktree_manager as wm
    from scripts.ops import mcp_gateway_durable as durable

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@x",
            "commit",
            "--allow-empty",
            "-qm",
            "base",
        ],
        check=True,
    )
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "--orphan", "other"], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@x",
            "commit",
            "--allow-empty",
            "-qm",
            "orphan",
        ],
        check=True,
    )
    orphan = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "main"], check=True, capture_output=True)
    (repo / ".git" / "info" / "grafts").write_text(f"{base} {orphan}\n", encoding="utf-8")
    inc = tmp_path / "included.gitconfig"
    inc.write_text("[core]\n\tcommitGraph = true\n", encoding="utf-8")
    if form == "pair":
        opts = ["-c", f"include.path={inc}"]
    elif form == "upper":
        opts = ["-c", f"INCLUDE.PATH={inc}"]
    elif form == "joined":
        opts = [f"-cinclude.path={inc}"]
    elif form == "gitdir":
        opts = ["-c", f"includeIf.gitdir:{repo}/.path={inc}"]
    elif form == "branch":
        opts = ["-c", f"includeif.onbranch:main.path={inc}"]
    elif form == "env_equal":
        monkeypatch.setenv("NEXUS_TEST_INCLUDE", str(inc))
        opts = ["--config-env=include.path=NEXUS_TEST_INCLUDE"]
    else:
        monkeypatch.setenv("NEXUS_TEST_INCLUDE", str(inc))
        opts = ["--config-env", "include.path=NEXUS_TEST_INCLUDE"]

    def run(*args):
        if wrapper == "worktree":
            return wm.WorktreeManager(
                root_dir=str(tmp_path / "targets"), create_root=False
            )._run_git([*opts, *args], cwd=repo)
        if wrapper == "unified":
            monkeypatch.setattr(unified, "CANONICAL_SOURCE_ROOT", repo)
            return unified._git(*opts, *args)
        return durable._git(repo, *opts, *args)

    assert run("config", "--get", "core.commitGraph").strip() == "false"
    assert orphan not in run("rev-list", "HEAD").splitlines()


def test_trusted_anchor_merge_base_ignores_grafts(tmp_path, monkeypatch):
    import subprocess

    from scripts.ops import trusted_deletion_anchor as anchor

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **__import__("os").environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    git("init", "-q")
    (repo / "a").write_text("a")
    git("add", "a")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    git("checkout", "--orphan", "orphan")
    git("rm", "-q", "-rf", ".")
    (repo / "b").write_text("b")
    git("add", "b")
    git("commit", "-qm", "orphan")
    orphan = git("rev-parse", "HEAD")
    (repo / ".git/info/grafts").write_text(f"{orphan} {base}\n")
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "merge-base", base, orphan], capture_output=True, env=env
        ).returncode
        == 0
    )
    with pytest.raises(ValueError, match="MERGE_BASE_NOT_UNIQUE"):
        anchor._unique_merge_base(repo, base, orphan)


def test_mcp_gateway_is_ancestor_ignores_grafts(tmp_path):
    import os
    import subprocess

    from scripts.ops import mcp_gateway_durable as gateway

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    git("init", "-q")
    (repo / "a").write_text("a")
    git("add", "a")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    git("checkout", "--orphan", "orphan")
    git("rm", "-q", "-rf", ".")
    (repo / "b").write_text("b")
    git("add", "b")
    git("commit", "-qm", "orphan")
    orphan = git("rev-parse", "HEAD")
    (repo / ".git/info/grafts").write_text(f"{orphan} {base}\n")
    assert not gateway._is_ancestor(repo, base, orphan)


def test_pr_preflight_git_wrapper_ignores_replace_ref(tmp_path):
    import os
    import subprocess

    from scripts.ops import pr_preflight as preflight

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    git("init", "-q")
    (repo / "a").write_text("a")
    git("add", "a")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    git("checkout", "--orphan", "orphan")
    git("rm", "-q", "-rf", ".")
    (repo / "b").write_text("b")
    git("add", "b")
    git("commit", "-qm", "orphan")
    orphan = git("rev-parse", "HEAD")
    git("replace", "--graft", orphan, base)
    assert preflight._git(repo, "merge-base", base, orphan, check=False).returncode != 0


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
        'def f():\n    e = history_pinned_env()\n    e2 = e\n    e2["GIT_NO_REPLACE_OBJECTS"] = "0"\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'def f():\n    e = history_pinned_env()\n    e.__setitem__("GIT_GRAFT_FILE", "x")\n    subprocess.run(["git", "rev-parse", "HEAD"], env=e)',
        'from subprocess import run\nrun(["git", "rev-list", "HEAD"])',
        'import subprocess as sp\nsp.run(["git", "log"])',
        'def f():\n    argv = ["git", "rev-list", "HEAD"]\n    subprocess.run(argv)',
        'subprocess.run(["git"] + args)',
        'subprocess.run([*prefix, "diff"])',
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
        'subprocess.run(["git"] + args, env=history_pinned_env())',
        'subprocess.run([*prefix, "diff"], env=history_pinned_env())',
    ],
)
def test_guard_accepts_pinned_or_non_history_calls(source):
    assert unpinned_history_calls(source) == []
