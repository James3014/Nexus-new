"""RED contract for scripts/governance/entrypoints_touched.py (#2612 S2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.governance import entrypoints_touched as et

REPO_ROOT = Path(__file__).resolve().parents[2]

GATEWAY = """\
from nexus.orchestrator.parts.mixin import _WorkMixin as _WorkMixin
from nexus.orchestrator.parts.mixin import TOOL_C as TOOL_C
from nexus.services import shared_dep
from nexus.services.only_a import helper_a

MODULE_CONSTANT = 1


class UnifiedMCPGateway(_WorkMixin):
    @staticmethod
    def tool_specs():
        return [
            {"name": "tool_a", "inputSchema": {}},
            {"name": "tool_b", "inputSchema": {}},
            {"name": "tool_c", "inputSchema": {}},
        ]

    def _call_tool(self, name, arguments):
        if name == "tool_a":
            return self._tool_a(arguments)
        if name == "tool_b":
            return self._tool_b(arguments)
        if name == TOOL_C:
            return self._tool_c(arguments)
        raise ValueError(name)

    def _tool_a(self, arguments):
        return helper_a(arguments)

    def _tool_b(self, arguments):
        value = arguments.get("x")
        return {"b": value}

    def _unused_helper(self):
        return shared_dep.thing()
"""

MIXIN = """\
from nexus.services.only_c import helper_c

TOOL_C = "tool_c"


def _local_helper(value):
    return helper_c(value)


class _WorkMixin:
    def _tool_c(self, arguments):
        return _local_helper(arguments)
"""

MAIN_SCRIPT = """\
import sys


def main():
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""

WORKFLOW = """\
name: demo
on: push
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: python3 -I scripts/ops/check.py --flag
      - run: python -m scripts.ops.module_job
"""

LAUNCHD = {
    "schema": "nexus.launchd_entrypoints.v1",
    "labels": {
        "com.nexus.mcp.gateway.direct": {"scripts": ["scripts/ops/gateway_http.py"]},
        "com.nexus.nightly": {"scripts": ["scripts/ops/nightly.py"]},
    },
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    files = {
        "nexus/__init__.py": "",
        "nexus/orchestrator/__init__.py": "",
        "nexus/orchestrator/unified_mcp_gateway.py": GATEWAY,
        "nexus/orchestrator/parts/__init__.py": "",
        "nexus/orchestrator/parts/mixin.py": MIXIN,
        "nexus/services/__init__.py": "",
        "nexus/services/shared_dep.py": "def thing():\n    return 1\n",
        "nexus/services/only_a.py": "from nexus.services import deep_a\n\n"
        "def helper_a(x):\n    return deep_a.f(x)\n",
        "nexus/services/deep_a.py": "def f(x):\n    return x\n",
        "nexus/services/only_c.py": "def helper_c(x):\n    return x\n",
        "nexus/services/cli_dep.py": "def run():\n    return 0\n",
        "nexus/services/unrelated.py": "def nothing():\n    return None\n",
        "scripts/__init__.py": "",
        "scripts/ops/__init__.py": "",
        "scripts/ops/gateway_http.py": "from nexus.orchestrator import unified_mcp_gateway\n",
        "scripts/ops/nightly.py": "from nexus.services import deep_a\n",
        "scripts/ops/check.py": "from nexus.services import unrelated\n",
        "scripts/ops/module_job.py": "from nexus.services import only_c\n",
        "scripts/ops/standalone.py": MAIN_SCRIPT,
        "scripts/engine/__init__.py": "",
        "scripts/engine/cli.py": "from nexus.services import cli_dep\n",
        "scripts/governance/launchd_entrypoints.json": json.dumps(LAUNCHD),
        ".github/workflows/demo.yml": WORKFLOW,
        "pyproject.toml": '[project]\nname = "demo"\n\n[project.scripts]\n'
        'nexus = "scripts.engine.cli:run"\n',
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(root.parent, "init", "-q", str(root))
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _commit_edit(repo: Path, rel: str, old: str, new: str) -> tuple[str, str]:
    base = _git(repo, "rev-parse", "HEAD")
    path = repo / rel
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))
    _git(repo, "commit", "-qam", "edit")
    return base, _git(repo, "rev-parse", "HEAD")


def _ids(report: dict) -> set[str]:
    return {row["id"] for row in report["entrypoints"]}


def _run(repo: Path, base: str, head: str) -> dict:
    changed, deleted, lines = et.changes_from_git(repo, base, head)
    return et.analyze(repo, changed, changed_lines=lines, deleted=deleted)


def test_dependency_used_only_by_one_tool_names_that_tool_and_the_gateway_launchd_job(repo):
    base, head = _commit_edit(repo, "nexus/services/deep_a.py", "return x", "return x + 1")
    report = _run(repo, base, head)
    ids = _ids(report)
    assert "gateway:tool_a" in ids
    assert "gateway:tool_b" not in ids and "gateway:tool_c" not in ids
    assert "launchd:com.nexus.mcp.gateway.direct" in ids
    assert "launchd:com.nexus.nightly" in ids
    assert report["schema"] == "nexus.entrypoints_touched.v1"
    assert report["unresolved"] == []
    assert report["gateway_tools_known"] == 3


def test_changed_line_inside_one_handler_names_only_that_tool(repo):
    base, head = _commit_edit(
        repo, "nexus/orchestrator/unified_mcp_gateway.py", '{"b": value}', '{"b": value, "v": 2}'
    )
    ids = _ids(_run(repo, base, head))
    assert {i for i in ids if i.startswith("gateway:")} == {"gateway:tool_b"}
    assert "launchd:com.nexus.mcp.gateway.direct" in ids


def test_tool_resolved_through_mixin_constant_name_and_same_file_function(repo):
    base, head = _commit_edit(repo, "nexus/services/only_c.py", "return x", "return -x")
    ids = _ids(_run(repo, base, head))
    assert "gateway:tool_c" in ids and "gateway:tool_a" not in ids
    base, head = _commit_edit(
        repo,
        "nexus/orchestrator/parts/mixin.py",
        "return helper_c(value)",
        "return helper_c(value * 2)",
    )
    assert {i for i in _ids(_run(repo, base, head)) if i.startswith("gateway:")} == {
        "gateway:tool_c"
    }


def test_module_level_or_unreached_gateway_change_is_gateway_star_not_every_tool(repo):
    base, head = _commit_edit(
        repo,
        "nexus/orchestrator/unified_mcp_gateway.py",
        "MODULE_CONSTANT = 1",
        "MODULE_CONSTANT = 2",
    )
    gateway_ids = {i for i in _ids(_run(repo, base, head)) if i.startswith("gateway:")}
    assert gateway_ids == {"gateway:*"}
    base, head = _commit_edit(repo, "nexus/services/shared_dep.py", "return 1", "return 3")
    gateway_ids = {i for i in _ids(_run(repo, base, head)) if i.startswith("gateway:")}
    assert gateway_ids == {"gateway:*"}


def test_tool_specs_entry_change_names_that_tool(repo):
    base, head = _commit_edit(
        repo,
        "nexus/orchestrator/unified_mcp_gateway.py",
        '{"name": "tool_b", "inputSchema": {}}',
        '{"name": "tool_b", "inputSchema": {"type": "object"}}',
    )
    assert {i for i in _ids(_run(repo, base, head)) if i.startswith("gateway:")} == {
        "gateway:tool_b"
    }


def test_changed_main_script_requires_a_real_run(repo):
    base, head = _commit_edit(repo, "scripts/ops/standalone.py", "return 0", "return 1")
    report = _run(repo, base, head)
    assert _ids(report) == {"script:scripts/ops/standalone.py"}
    row = report["entrypoints"][0]
    assert row["kind"] == "script" and row["via"] == ["scripts/ops/standalone.py"]


def test_console_script_and_workflows_by_path_and_module(repo):
    base, head = _commit_edit(repo, "nexus/services/cli_dep.py", "return 0", "return 2")
    assert _ids(_run(repo, base, head)) == {"console:nexus"}
    base, head = _commit_edit(repo, "nexus/services/unrelated.py", "return None", "return 0")
    assert _ids(_run(repo, base, head)) == {"workflow:.github/workflows/demo.yml"}
    base, head = _commit_edit(repo, ".github/workflows/demo.yml", "name: demo", "name: demo2")
    assert _ids(_run(repo, base, head)) == {"workflow:.github/workflows/demo.yml"}
    base, head = _commit_edit(repo, "nexus/services/only_c.py", "return x", "return -x")
    assert "workflow:.github/workflows/demo.yml" in _ids(_run(repo, base, head))


def test_unreachable_change_names_nothing_and_deleted_files_are_listed(repo):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "nexus/services/stray.py").write_text("X = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "rm", "-q", "scripts/ops/check.py")
    _git(repo, "commit", "-qm", "stray")
    report = _run(repo, base, _git(repo, "rev-parse", "HEAD"))
    assert report["entrypoints"] == []
    assert report["deleted_files"] == ["scripts/ops/check.py"]


def test_missing_gateway_class_is_reported_unresolved(repo):
    base, head = _commit_edit(
        repo,
        "nexus/orchestrator/unified_mcp_gateway.py",
        "class UnifiedMCPGateway(",
        "class Renamed(",
    )
    report = _run(repo, base, head)
    assert any("UnifiedMCPGateway not found" in u for u in report["unresolved"])
    assert report["gateway_tools_known"] == 0


def test_cli_requires_checkout_at_head_and_emits_json(repo, tmp_path):
    base, head = _commit_edit(repo, "nexus/services/deep_a.py", "return x", "return x * 3")
    script = REPO_ROOT / "scripts/governance/entrypoints_touched.py"
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    out = tmp_path / "out.json"
    ok = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo),
            "--base",
            base,
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert ok.returncode == 0, ok.stderr
    data = json.loads(out.read_text())
    assert data["base"] == base and data["head"] == head and "gateway:tool_a" in _ids(data)
    bad = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo), "--base", base, "--head", base],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert bad.returncode == 2 and "checked out at --head" in bad.stderr


def test_checked_in_launchd_map_points_at_tracked_scripts():
    data = json.loads((REPO_ROOT / et.LAUNCHD_MAP).read_text())
    assert data["schema"] == "nexus.launchd_entrypoints.v1"
    assert "com.nexus.mcp.gateway.direct" in data["labels"]
    for label, entry in data["labels"].items():
        assert label.startswith("com.nexus."), label
        for script in entry["scripts"]:
            assert (REPO_ROOT / script).is_file(), (label, script)


def test_real_gateway_resolves_every_tool_spec_to_a_handler():
    report = et.analyze(
        REPO_ROOT, ["nexus/orchestrator/unified_mcp_gateway_parts/worker_candidate.py"]
    )
    assert report["unresolved"] == []
    assert report["gateway_tools_known"] >= 40
    assert "gateway:nexus_worker_candidate" in _ids(report)
    assert "launchd:com.nexus.mcp.gateway.direct" in _ids(report)


def _to_elif_chain(repo: Path) -> None:
    path = repo / "nexus/orchestrator/unified_mcp_gateway.py"
    text = path.read_text()
    text = text.replace('        if name == "tool_b":', '        elif name == "tool_b":')
    text = text.replace("        if name == TOOL_C:", "        elif name == TOOL_C:")
    path.write_text(text)
    _git(repo, "commit", "-qam", "elif chain")


def test_elif_chain_branch_span_excludes_the_following_branches(repo):
    _to_elif_chain(repo)
    base, head = _commit_edit(
        repo,
        "nexus/orchestrator/unified_mcp_gateway.py",
        "return self._tool_c(arguments)",
        "return self._tool_c(dict(arguments))",
    )
    report = _run(repo, base, head)
    assert report["unresolved"] == []
    assert {i for i in _ids(report) if i.startswith("gateway:")} == {"gateway:tool_c"}
    # A dependency of tool_c alone is not attributed to tool_a, whose If holds tool_c in orelse.
    base, head = _commit_edit(repo, "nexus/services/only_c.py", "return x", "return -x")
    assert {i for i in _ids(_run(repo, base, head)) if i.startswith("gateway:")} == {
        "gateway:tool_c"
    }


def test_edit_inside_a_call_tool_branch_names_only_that_tool(repo):
    base, head = _commit_edit(
        repo,
        "nexus/orchestrator/unified_mcp_gateway.py",
        "return self._tool_b(arguments)",
        "return self._tool_b(dict(arguments))",
    )
    assert {i for i in _ids(_run(repo, base, head)) if i.startswith("gateway:")} == {
        "gateway:tool_b"
    }


@pytest.mark.parametrize(
    "labels",
    [
        {"com.nexus.bad": "scripts/ops/nightly.py"},
        {"com.nexus.bad": ["scripts/ops/nightly.py"]},
        {"com.nexus.bad": {"scripts": "scripts/ops/nightly.py"}},
        {"com.nexus.bad": {"scripts": [1]}},
    ],
)
def test_malformed_launchd_label_raises_entrypoints_error(repo, labels):
    path = repo / et.LAUNCHD_MAP
    path.write_text(json.dumps({"schema": "nexus.launchd_entrypoints.v1", "labels": labels}))
    with pytest.raises(et.EntrypointsError, match="malformed"):
        et.analyze(repo, ["nexus/services/deep_a.py"])
    path.write_text(json.dumps(["not", "a", "mapping"]))
    with pytest.raises(et.EntrypointsError, match="malformed"):
        et.analyze(repo, ["nexus/services/deep_a.py"])
