"""Guard for the 2026-10-21 Phase-2 dead-code retirement (batch B, Issue #2584).

See ARCHIVED_2026-10-21_phase2_batch_B.md. The modules, scripts and self-hosted MCP
tools below were physically deleted after an Owner decision. These tests fail if one
comes back (as a module, a package, a same-named data file or a script), or if code
under nexus/ or scripts/ (archive excluded) starts importing or naming one again, so
re-adding is deliberate.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("nexus", "scripts")
SCAN_EXCLUDED_PREFIXES = ("scripts/archive/",)
TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".cfg",
    ".ini",
    ".sh",
    ".html",
    ".plist",
}
REAPPEAR_SUFFIXES = (".py", ".json", ".txt")

# Python modules (dotted name -> repo path without suffix).
RETIRED_MODULES = (
    "nexus.orchestrator.refactor_campaign",
    "nexus.orchestrator.worker_competition",
    "nexus.core.planner_auditor",
    "scripts.ops.codex_run_guard",
    "scripts.tg_pty_bridge",
    "scripts.script_dashboard",
    "scripts.morning_briefing",
)
# Every deleted non-test file, by repo path.
RETIRED_FILES = (
    "nexus/orchestrator/refactor_campaign.py",
    "nexus/orchestrator/worker_competition.py",
    "nexus/core/planner_auditor.py",
    "scripts/ops/start_codex_nexus_enforced.sh",
    "scripts/ops/start_antigravity_nexus_enforced.sh",
    "scripts/ops/codex_run_guard.py",
    "scripts/tg_pty_bridge.py",
    "scripts/script_dashboard.py",
    "scripts/morning_briefing.py",
    "scripts/Swarm_Dashboard.html",
)
# Self-hosted MCP tools removed from nexus/orchestrator/self_hosted_mcp.py.
RETIRED_TOOLS = (
    "nexus_self_hosted_compete_task",
    "nexus_self_hosted_get_competition",
    "nexus_self_hosted_integrate_competition",
    "nexus_self_hosted_create_refactor_campaign",
    "nexus_self_hosted_advance_refactor_campaign",
    "nexus_self_hosted_get_refactor_campaign",
    "nexus_self_hosted_rollback_refactor_campaign",
    "nexus_self_hosted_push_competition",
)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(path: Path, tree: ast.AST) -> set[str]:
    """Absolute dotted names a module imports (relative imports resolved)."""
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")
                if node.level > 1:
                    anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            first = node.args[0]
            if (
                called in {"import_module", "__import__", "find_spec"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                names.add(first.value)
    return names


def _is_retired(name: str) -> bool:
    return any(name == retired or name.startswith(retired + ".") for retired in RETIRED_MODULES)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for top in SCAN_ROOTS:
        for path in sorted((REPO_ROOT / top).rglob("*")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "__pycache__" in path.parts or rel.startswith(SCAN_EXCLUDED_PREFIXES):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                files.append(path)
    return files


def _name_pattern() -> re.Pattern[str]:
    alternatives = [rf"\b{re.escape(module)}\b" for module in RETIRED_MODULES]
    alternatives += [rf"\b{re.escape(rel)}\b" for rel in RETIRED_FILES]
    alternatives += [rf"\b{re.escape(tool)}\b" for tool in RETIRED_TOOLS]
    return re.compile("|".join(alternatives))


@pytest.mark.parametrize("rel", RETIRED_FILES)
def test_retired_phase2_batch_b_path_absent(rel: str) -> None:
    path = REPO_ROOT / rel
    base = path.with_suffix("")
    present = [
        str(p.relative_to(REPO_ROOT))
        for p in (path, base, *(base.with_suffix(s) for s in REAPPEAR_SUFFIXES))
        if p.exists()
    ]
    assert present == [], f"retired in #2584 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_phase2_batch_b_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2584) but is importable again"


def test_retired_phase2_batch_b_not_imported() -> None:
    offenders: list[str] = []
    for path in _scanned_files():
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            continue  # the text scan below still covers this file
        hits = sorted(name for name in _imported_modules(path, tree) if _is_retired(name))
        offenders.extend(f"{path.relative_to(REPO_ROOT)}: {name}" for name in hits)
    assert offenders == []


def test_retired_phase2_batch_b_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_retired_phase2_batch_b_mcp_tools_not_served() -> None:
    from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer

    served = {spec["name"] for spec in NexusSelfHostedMCPServer._tool_specs()}
    assert served, "self-hosted MCP tool list is empty: the scan would be vacuous"
    assert "nexus_self_hosted_submit_task" in served
    assert served.isdisjoint(RETIRED_TOOLS)


def test_retired_phase2_batch_b_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of a retired item is flagged."""
    sample = REPO_ROOT / "nexus" / "orchestrator" / "sample.py"
    for source in (
        "import nexus.orchestrator.worker_competition\n",
        "from nexus.orchestrator import refactor_campaign\n",
        "from .worker_competition import WorkerCompetitionCoordinator\n",
        "from ..core.planner_auditor import PlannerAuditor\n",
        "from scripts.ops import codex_run_guard\n",
        "importlib.import_module('scripts.script_dashboard')\n",
        "importlib.util.find_spec('nexus.core.planner_auditor')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    for kept in (
        "from .self_hosted_mcp import NexusSelfHostedMCPServer\n",
        "from .governed_push import GovernedPushManager\n",
        "from nexus.executors import codex_run_boundary\n",
    ):
        assert not any(_is_retired(name) for name in _imported_modules(sample, ast.parse(kept)))
    pattern = _name_pattern()
    assert pattern.search("bash scripts/ops/start_codex_nexus_enforced.sh gpt-5 workspace-write")
    assert pattern.search('"script": "scripts/tg_pty_bridge.py"')
    assert pattern.search("open scripts/Swarm_Dashboard.html")
    assert pattern.search('{"name": "nexus_self_hosted_push_competition"}')
    assert not pattern.search("scripts/ops/start_gemini_nexus_enforced.sh")
    assert not pattern.search("nexus/executors/codex_run_boundary.py nexus_self_hosted_submit_task")
