#!/usr/bin/env python3
"""Deterministic AST dependency map of ``nexus/orchestrator/self_hosted_task_service.py``.

Phase 5b-0 / 5c measurement tool (stdlib only, no production imports).  It
classifies every import, computes per-definition external references, partitions
definitions into first-cut ``runtime_candidate`` / ``bridge_candidate`` / ``stay``
clusters, lists string-form patch sites in ``tests/**`` and counts in-repo
importers of the 5c parallel-implementation candidates.

Usage:
    python scripts/ops/self_hosted_task_service_dependency_map.py            # write JSON
    python scripts/ops/self_hosted_task_service_dependency_map.py --stdout   # print JSON
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_REL = "nexus/orchestrator/self_hosted_task_service.py"
OUTPUT_REL = "docs/plans/self_hosted_task_service_dependency_map.json"
SERVICE_CLASS = "SelfHostedTaskService"
MODULE_NAME = "nexus.orchestrator.self_hosted_task_service"

# Files that mention the module/candidate names by construction; never counted.
SELF_EXCLUDED = (
    "scripts/ops/self_hosted_task_service_dependency_map.py",
    "tests/architecture/test_self_hosted_task_service_dependency_map.py",
)

# Sovereign modules (derived from the actual import list of the source file).
# module -> (category, reason)
SOVEREIGN_MODULES: dict[str, tuple[str, str]] = {
    "nexus.contracts.workforce_admission": ("workforce_admission", "WorkforceDemand contract"),
    "nexus.services.runtime_workforce_admission": (
        "workforce_dispatch_binding",
        "evaluate_runtime_workforce_admission / binding payload",
    ),
    "nexus.services.model_workforce_policy": ("workforce_admission", "WorkforcePolicyLoader"),
    "nexus.orchestrator.acceptance_loop": ("acceptance_loop", "candidate acceptance reducer"),
    "nexus.orchestrator.autonomy_policy": ("autonomy_policy", "autonomy submission projection"),
    "nexus.contracts.autonomy_goal": ("autonomy_policy", "autonomy goal grant contract"),
    "nexus.services.mainchain_entry": (
        "capability_registry",
        "mainchain capability invokers (function-local import)",
    ),
    "nexus.services.unified_runtime": (
        "capability_registry",
        "selected capability evidence (function-local import)",
    ),
}
# Substring patterns: any imported module matching is sovereign automatically.
SOVEREIGN_PATTERNS: dict[str, str] = {
    "capability_registry": "capability_registry",
    "local_heal": "local_heal",
    "gateway": "gateway",
}
# MCP tool projection has no module of its own in this file; detected by name.
MCP_NAME_RE = re.compile(r"mcp|projection", re.IGNORECASE)
# Sovereignty by name: workforce dispatch/admission, acceptance and autonomy
# logic keeps its authority even when the import is indirect (via in-module code).
SOVEREIGN_NAME_RE = re.compile(r"workforce|acceptance|autonomy|capability", re.IGNORECASE)

PARALLEL_CANDIDATES: dict[str, dict[str, Any]] = {
    "nexus/retry_policy/": {"modules": ["nexus.retry_policy"], "pathspec": "nexus/retry_policy/"},
    "nexus/core/handoff_*.py": {
        "modules": ["nexus.core.handoff_builder", "nexus.core.handoff_bundle"],
        "pathspec": "nexus/core/handoff_*.py",
    },
    "nexus/services/local_heal/p3_local_retry_stub*.py": {
        "modules": [
            "nexus.services.local_heal.p3_local_retry_stub",
            "nexus.services.local_heal.p3_local_retry_stub_runtime",
        ],
        "pathspec": "nexus/services/local_heal/p3_local_retry_stub*.py",
    },
    "nexus/services/m5_local/handoff_adapter.py": {
        "modules": ["nexus.services.m5_local.handoff_adapter"],
        "pathspec": "nexus/services/m5_local/handoff_adapter.py",
    },
    "nexus/experimental/c6bd_preimage_retry.py": {
        "modules": ["nexus.experimental.c6bd_preimage_retry"],
        "pathspec": "nexus/experimental/c6bd_preimage_retry.py",
    },
}


def classify_module(module: str) -> str:
    root = module.split(".")[0]
    if root == "nexus_runtime":
        return "nexus_runtime"
    if root == "nexus":
        return "nexus-new"
    if root in sys.stdlib_module_names:
        return "stdlib"
    return "third-party"


def sovereign_category(module: str) -> str | None:
    if module in SOVEREIGN_MODULES:
        return SOVEREIGN_MODULES[module][0]
    for needle, category in SOVEREIGN_PATTERNS.items():
        if needle in module:
            return category
    return None


class _ImportCollector(ast.NodeVisitor):
    """Collect imports with their bound names; track the enclosing definition."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.records.append(
                {
                    "module": alias.name,
                    "name": None,
                    "bound": alias.asname or alias.name.split(".")[0],
                    "lineno": node.lineno,
                }
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = ("." * node.level) + (node.module or "")
        for alias in node.names:
            self.records.append(
                {
                    "module": module,
                    "name": alias.name,
                    "bound": alias.asname or alias.name,
                    "lineno": node.lineno,
                }
            )


def _span(node: ast.AST) -> tuple[int, int]:
    start = node.lineno  # type: ignore[attr-defined]
    decorators = getattr(node, "decorator_list", [])
    if decorators:
        start = min(start, min(d.lineno for d in decorators))
    return start, node.end_lineno  # type: ignore[attr-defined]


def _assign_names(node: ast.stmt) -> list[str]:
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    return [t.id for t in targets if isinstance(t, ast.Name)]


def build_definitions(tree: ast.Module) -> list[dict[str, Any]]:
    """Top-level classes/functions/constants plus methods of the service class."""
    defs: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = _span(node)
            defs.append({"name": node.name, "kind": "function", "node": node, "start": start, "end": end})
        elif isinstance(node, ast.ClassDef):
            start, end = _span(node)
            defs.append({"name": node.name, "kind": "class", "node": node, "start": start, "end": end})
            if node.name == SERVICE_CLASS:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        s, e = _span(item)
                        defs.append(
                            {
                                "name": f"{SERVICE_CLASS}.{item.name}",
                                "kind": "method",
                                "node": item,
                                "start": s,
                                "end": e,
                            }
                        )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = _assign_names(node)
            if names:
                start, end = _span(node)
                defs.append({"name": names[0], "kind": "constant", "node": node, "start": start, "end": end})
    return defs


def analyse(tree: ast.Module, text: str) -> dict[str, Any]:
    # Module-level import table (name -> module) and all imports (any scope).
    collector = _ImportCollector()
    collector.visit(tree)
    top_level_linenos = {
        n.lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
    }
    module_table: dict[str, str] = {}
    imports_by_module: dict[str, dict[str, Any]] = {}
    for rec in collector.records:
        scope = "module" if rec["lineno"] in top_level_linenos else "function-local"
        entry = imports_by_module.setdefault(
            rec["module"],
            {"module": rec["module"], "names": set(), "scopes": set(), "lines": set()},
        )
        if rec["name"]:
            entry["names"].add(rec["name"])
        entry["scopes"].add(scope)
        entry["lines"].add(rec["lineno"])
        if scope == "module":
            module_table[rec["bound"]] = rec["module"]

    imports = []
    for module in sorted(imports_by_module):
        entry = imports_by_module[module]
        imports.append(
            {
                "classification": classify_module(module),
                "first_line": min(entry["lines"]),
                "module": module,
                "names": sorted(entry["names"]),
                "scopes": sorted(entry["scopes"]),
                "sovereign_category": sovereign_category(module),
            }
        )

    raw_defs = build_definitions(tree)
    module_def_names = {d["name"] for d in raw_defs if d["kind"] != "method"}
    method_names = {d["name"].split(".", 1)[1] for d in raw_defs if d["kind"] == "method"}

    definitions: list[dict[str, Any]] = []
    for d in raw_defs:
        node = d["node"]
        # Function-local imports bind names inside this definition only.
        local = _ImportCollector()
        local.visit(node)
        table = dict(module_table)
        for rec in local.records:
            table[rec["bound"]] = rec["module"]
        ext_names: set[str] = set()
        in_module: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                if sub.id in table:
                    ext_names.add(sub.id)
                elif sub.id in module_def_names and sub.id != d["name"]:
                    in_module.add(sub.id)
            elif (
                isinstance(sub, ast.Attribute)
                and isinstance(sub.value, ast.Name)
                and sub.value.id in ("self", "cls", SERVICE_CLASS)
                and sub.attr in method_names
                and f"{SERVICE_CLASS}.{sub.attr}" != d["name"]
            ):
                in_module.add(f"{SERVICE_CLASS}.{sub.attr}")
        modules = sorted({table[n] for n in ext_names})
        kinds: dict[str, list[str]] = {"nexus-new": [], "nexus_runtime": [], "stdlib": [], "third-party": []}
        for m in modules:
            kinds[classify_module(m)].append(m)
        sovereign = sorted({m for m in kinds["nexus-new"] if sovereign_category(m)})
        simple = d["name"].split(".")[-1]
        definitions.append(
            {
                "end_line": d["end"],
                "external_names": sorted(ext_names),
                "in_module_refs": sorted(in_module),
                "kind": d["kind"],
                "lines": d["end"] - d["start"] + 1,
                "mcp_projection": bool(MCP_NAME_RE.search(simple)),
                "name": d["name"],
                "sovereign_by_name": bool(SOVEREIGN_NAME_RE.search(simple)),
                "nexus_modules": sorted(kinds["nexus-new"]),
                "nexus_runtime_modules": sorted(kinds["nexus_runtime"]),
                "sovereign_modules": sovereign,
                "start_line": d["start"],
                "stdlib_modules": sorted(kinds["stdlib"]),
                "third_party_modules": sorted(kinds["third-party"]),
            }
        )

    assign_clusters(definitions)
    clusters = summarise_clusters(definitions)
    return {
        "imports": imports,
        "definitions": definitions,
        "clusters": clusters,
        "sovereign_modules": sorted(
            {
                i["module"]: {
                    "category": i["sovereign_category"],
                    "module": i["module"],
                }
                for i in imports
                if i["sovereign_category"]
            }.values(),
            key=lambda x: x["module"],
        ),
        "sovereign_categories_without_import": sorted(
            {"capability_registry", "local_heal", "gateway", "mcp_tool_projection"}
            - {i["sovereign_category"] for i in imports if i["sovereign_category"]}
            | {"mcp_tool_projection"}
        ),
    }


def assign_clusters(definitions: list[dict[str, Any]]) -> None:
    by_name = {d["name"]: d for d in definitions}
    for d in definitions:
        d["cluster"] = None
        d["reason"] = ""
    clusterable = [d for d in definitions if not (d["kind"] == "class" and d["name"] == SERVICE_CLASS)]

    # reaches_sovereign: transitive over the in-module reference graph.
    reach = {
        d["name"]: bool(d["sovereign_modules"] or d["mcp_projection"] or d["sovereign_by_name"])
        for d in definitions
    }
    changed = True
    while changed:
        changed = False
        for d in definitions:
            if not reach[d["name"]] and any(reach.get(r) for r in d["in_module_refs"]):
                reach[d["name"]] = True
                changed = True
    for d in definitions:
        d["reaches_sovereign_transitively"] = reach[d["name"]]

    # runtime candidates: greatest fixed point.
    runtime = {
        d["name"]
        for d in clusterable
        if not d["nexus_modules"]
        and not d["third_party_modules"]
        and not d["sovereign_modules"]
        and not d["mcp_projection"]
        and not d["sovereign_by_name"]
    }
    changed = True
    while changed:
        changed = False
        for name in sorted(runtime):
            refs = by_name[name]["in_module_refs"]
            if any((r not in runtime) for r in refs if r in by_name and by_name[r] in clusterable):
                runtime.discard(name)
                changed = True
            elif any(r == f"{SERVICE_CLASS}" for r in refs):
                runtime.discard(name)
                changed = True

    for d in clusterable:
        if d["name"] in runtime:
            d["cluster"] = "runtime_candidate"
            d["reason"] = "stdlib/nexus_runtime and runtime_candidate refs only"
        elif d["sovereign_modules"]:
            d["cluster"] = "stay"
            d["reason"] = "references sovereign module(s)"
        elif d["mcp_projection"]:
            d["cluster"] = "stay"
            d["reason"] = "MCP/projection by name"
        elif d["sovereign_by_name"]:
            d["cluster"] = "stay"
            d["reason"] = "workforce/acceptance/autonomy/capability by name"
        elif len(d["nexus_modules"]) <= 2:
            d["cluster"] = "bridge_candidate"
            d["reason"] = "<=2 nexus-new modules, none sovereign"
        else:
            d["cluster"] = "stay"
            d["reason"] = ">2 nexus-new modules"


def summarise_clusters(definitions: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ("runtime_candidate", "bridge_candidate", "stay"):
        members = [d for d in definitions if d["cluster"] == name]
        out[name] = {
            "count": len(members),
            "definitions": sorted(d["name"] for d in members),
            "total_lines": sum(d["lines"] for d in members),
        }
    return out


def _git_grep(repo: Path, pattern: str, pathspecs: list[str]) -> list[tuple[str, int, str]]:
    cmd = ["git", "grep", "-n", "-I", "-E", "-e", pattern, "--", *pathspecs]
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[1].isdigit():
            rows.append((parts[0], int(parts[1]), parts[2]))
    return sorted(rows)


def string_patch_sites(repo: Path) -> list[dict[str, Any]]:
    # Prefix built by concatenation so this file never matches itself.
    prefix = re.escape(MODULE_NAME) + r"\.[A-Za-z_][A-Za-z0-9_.]*"
    pattern = "[\"']" + prefix + "[\"']"
    pathspecs = ["tests/**"] + [f":(exclude){p}" for p in SELF_EXCLUDED]
    sites = []
    for path, lineno, text in _git_grep(repo, pattern, pathspecs):
        for match in re.finditer(pattern, text):
            target = match.group(0)[1:-1]
            sites.append(
                {
                    "attribute": target[len(MODULE_NAME) + 1 :],
                    "file": path,
                    "line": lineno,
                    "target": target,
                }
            )
    return sites


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or "/tests/" in path or name.startswith("test_")


def parallel_implementations(repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, cfg in PARALLEL_CANDIDATES.items():
        own = subprocess.run(
            ["git", "ls-files", "--", cfg["pathspec"]],
            cwd=repo, capture_output=True, text=True, check=False,
        ).stdout.split()
        own_dirs = tuple(p for p in own)
        alt = "|".join(re.escape(m) for m in cfg["modules"])
        pattern = rf"(^|[^A-Za-z0-9_.])({alt})([^A-Za-z0-9_]|$)"
        # Also catch ``from nexus.core import handoff_builder`` style.
        pkg_forms = []
        for m in cfg["modules"]:
            parent, _, leaf = m.rpartition(".")
            pkg_forms.append(rf"from {re.escape(parent)} import .*\b{re.escape(leaf)}\b")
        full = "(" + pattern + ")|(" + "|".join(pkg_forms) + ")"
        pathspecs = ["*.py"] + [f":(exclude){p}" for p in SELF_EXCLUDED]
        importers: dict[str, list[int]] = {}
        other: dict[str, list[int]] = {}
        for path, lineno, text in _git_grep(repo, full, pathspecs):
            if path in own_dirs:
                continue
            stripped = text.strip()
            is_import = bool(re.match(r"(from|import)\s", stripped))
            (importers if is_import else other).setdefault(path, []).append(lineno)
        imp_files = sorted(importers)
        result[label] = {
            "candidate_files": sorted(own),
            "importers_non_test": [p for p in imp_files if not _is_test_path(p)],
            "importers_test": [p for p in imp_files if _is_test_path(p)],
            "importer_counts": {
                "non_test": sum(1 for p in imp_files if not _is_test_path(p)),
                "test": sum(1 for p in imp_files if _is_test_path(p)),
            },
            "string_or_other_reference_files": sorted(p for p in other if p not in importers),
        }
    return result


def build_map(repo: Path = REPO_ROOT) -> dict[str, Any]:
    source = repo / SOURCE_REL
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text)
    data = analyse(tree, text)
    data["source"] = {
        "lines": len(text.splitlines()),
        "path": SOURCE_REL,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    data["string_patch_sites"] = string_patch_sites(repo)
    data["string_patch_site_count"] = len(data["string_patch_sites"])
    data["parallel_implementations"] = parallel_implementations(repo)
    return data


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def render_markdown(d: dict[str, Any]) -> str:
    by = {x["name"]: x for x in d["definitions"]}
    out: list[str] = []
    out.append("# self_hosted_task_service dependency map (Phase 5b-0 measurement)\n")
    out.append(
        f"Generated by `scripts/ops/self_hosted_task_service_dependency_map.py` from "
        f"`{d['source']['path']}` ({d['source']['lines']} lines). Machine-readable data: "
        f"`{OUTPUT_REL}`; drift is reported by "
        "`tests/architecture/test_self_hosted_task_service_dependency_map.py` (GAP skip) and "
        "`--check`. Refresh with `python scripts/ops/self_hosted_task_service_dependency_map.py --write`.\n"
    )
    out.append(
        "The partition is a first cut based on direct static references (imports, in-module "
        "references); `runtime_candidate` is necessary, not sufficient (methods still touch "
        "`self` state). No production code was changed.\n"
    )
    out.append("## Clusters\n\n| cluster | definitions | lines |\n|---|---:|---:|")
    for k, v in d["clusters"].items():
        out.append(f"| {k} | {v['count']} | {v['total_lines']} |")
    out.append(
        f"\nThe `{SERVICE_CLASS}` class record itself (~{by[SERVICE_CLASS]['lines']} lines) "
        "is not clustered; its methods are.\n"
    )
    out.append(
        "Rules: `stay` = references a sovereign module, MCP/projection by name, "
        "workforce/acceptance/autonomy/capability by name, or more than 2 nexus-new modules; "
        "`bridge_candidate` = at most 2 nexus-new modules, none sovereign; `runtime_candidate` = "
        "only stdlib, `nexus_runtime`, and other runtime candidates.\n"
    )
    out.append("## Top 15 largest definitions\n\n| # | definition | lines | cluster |\n|---:|---|---:|---|")
    top = sorted((x for x in d["definitions"] if x["cluster"]), key=lambda x: (-x["lines"], x["name"]))[:15]
    for i, x in enumerate(top, 1):
        out.append(f"| {i} | `{x['name']}` | {x['lines']} | {x['cluster']} |")
    out.append("\n## Sovereign modules (derived from the import list)\n\n| module | category |\n|---|---|")
    for m in d["sovereign_modules"]:
        out.append(f"| `{m['module']}` | {m['category']} |")
    out.append(
        "\nNo import of `capability_registry`, `local_heal` or `gateway` modules exists in this "
        "file (`mainchain_entry` / `unified_runtime`, function-local, are treated as the capability "
        "surface). MCP tool projection has no module; it is detected by definition name "
        "(`mcp|projection`).\n"
    )
    out.append(
        f"## String-form patch sites\n\n{d['string_patch_site_count']} string-form targets under "
        "`tests/**` (file:line list in the JSON under `string_patch_sites`); these break when "
        "definitions move.\n"
    )
    out.append(
        "## Parallel implementations (5c importers via git grep)\n\n"
        "| candidate | importers non-test | importers test |\n|---|---:|---:|"
    )
    for k, v in d["parallel_implementations"].items():
        out.append(f"| `{k}` | {v['importer_counts']['non_test']} | {v['importer_counts']['test']} |")
    out.append("\n## Recommended 5b-1 first slice: status sets\n")
    sets = [x for x in d["definitions"] if x["name"].endswith("_STATUSES")]
    out.append(
        "All ten status-set constants are `runtime_candidate` (stdlib only):\n\n"
        "| definition | lines | in-module consumers |\n|---|---:|---:|"
    )
    for x in sets:
        n = sum(1 for y in d["definitions"] if x["name"] in y["in_module_refs"] and y["name"] != SERVICE_CLASS)
        out.append(f"| `{x['name']}` | {x['lines']} | {n} |")
    out.append(
        f"\nTotal: {sum(x['lines'] for x in sets)} lines. The source has no standalone transition "
        "function; the consumers are methods (e.g. `_validate_retry_predecessor` uses "
        "`RETRYABLE_TASK_STATUSES`; `_task_action_envelope`, `_validate_state_payload` are runtime "
        "candidates but are `self`-bound methods and are out of the first slice). "
        "`nexus/orchestrator/runtime_coordination_bridge.py` reads `TERMINAL_STATUSES` via the "
        "service module, so the service must re-export the names after the move."
    )
    return "\n".join(out) + "\n"


MARKDOWN_REL = "docs/plans/SELF_HOSTED_TASK_SERVICE_DEPENDENCY_MAP.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--stdout", action="store_true", help="print JSON instead of writing")
    group.add_argument("--check", action="store_true", help="exit 1 if committed JSON+MD drifted")
    group.add_argument("--write", action="store_true", help="refresh committed JSON and MD (default)")
    args = parser.parse_args(argv)
    data = build_map()
    out = render(data)
    md = render_markdown(data)
    if args.stdout:
        sys.stdout.write(out)
        return 0
    json_path, md_path = REPO_ROOT / OUTPUT_REL, REPO_ROOT / MARKDOWN_REL
    if args.check:
        stale = [
            rel
            for rel, path, text in ((OUTPUT_REL, json_path, out), (MARKDOWN_REL, md_path, md))
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]
        if stale:
            sys.stderr.write("dependency map stale: " + ", ".join(stale) + "\n")
            return 1
        return 0
    json_path.write_text(out, encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
