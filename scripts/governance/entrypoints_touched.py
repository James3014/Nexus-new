#!/usr/bin/env python3
"""Which real entry points can reach a change? (#2612 S2). Read-only.

Output: ``nexus.entrypoints_touched.v1`` JSON for
``scripts/governance/promise_confirmation.py --entrypoints-json``.

The file-level import graph is ``scripts/ops/rie_pr_comment.build_import_graph``
(the same AST graph RIE ``impact`` uses). The entry registry is:

- ``gateway:<tool>``: every tool named in ``UnifiedMCPGateway.tool_specs()``,
  resolved to its handler through the ``_call_tool`` if-chain, then through
  ``self.<method>`` calls (the class and its mixin bases) and same-file
  functions. A tool is touched when a changed line falls inside a function its
  handler reaches (or its ``tool_specs`` entry), or when a changed file is
  imported, directly or transitively, by a name that handler code uses.
  ``gateway:*`` means the Gateway process reaches the change but no single
  tool could be attributed (module-level code, unreached helpers).
- ``console:nexus``: the ``[project.scripts]`` target module.
- ``workflow:<path>``: a workflow whose file changed, or that runs a ``.py``
  path (or ``python -m`` module) the change reaches.
- ``launchd:<label>``: ``scripts/governance/launchd_entrypoints.json``.
- ``script:<path>``: a changed file that has an ``if __name__ == "__main__"``
  block.

Limits (reported in ``limitations``): static AST only; attribute calls on
locals (``g = _gateway(); g.f()``), ``getattr`` and string dispatch are not
followed; deleted files are listed, not resolved.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
import warnings
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.rie_pr_comment import _module_name, _resolve, build_import_graph  # noqa: E402

SCHEMA = "nexus.entrypoints_touched.v1"
GATEWAY_FILE = "nexus/orchestrator/unified_mcp_gateway.py"
GATEWAY_CLASS = "UnifiedMCPGateway"
LAUNCHD_MAP = "scripts/governance/launchd_entrypoints.json"
WORKFLOW_DIR = ".github/workflows/"
MAX_VIA = 5
LIMITATIONS = (
    "static AST only: attribute calls on local variables, getattr and string dispatch are "
    "not followed",
    "file-level import reachability: a changed file reached by an entry point does not prove "
    "the changed code runs there",
    "deleted files are listed in deleted_files and not resolved",
)
_PY_PATH = re.compile(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)(?![A-Za-z0-9_])")
_PY_MODULE = re.compile(r"python[0-9.]*(?:\s+-[A-Za-z]+)*\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class EntrypointsError(RuntimeError):
    pass


# ----------------------------------------------------------------- git input


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise EntrypointsError(f"git {args[0]} failed") from exc
    return proc.stdout


def changes_from_git(repo: Path, base: str, head: str) -> tuple[list[str], list[str], dict]:
    """(changed paths at head, deleted paths, head line numbers changed per path)."""
    changed, deleted = [], []
    for line in _git(repo, "diff", "--name-status", "-M", base, head).splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0][0]
        if status == "D":
            deleted.append(parts[1])
        elif status in "RC":
            changed.append(parts[2])
        else:
            changed.append(parts[1])
    lines: dict[str, set[int]] = {}
    current = None
    for line in _git(repo, "diff", "-U0", "-M", "--no-color", base, head).splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = target[2:] if target.startswith("b/") else None
            if current is not None:
                lines.setdefault(current, set())
            continue
        match = _HUNK.match(line)
        if match and current is not None:
            start, count = int(match.group(1)), int(match.group(2) or "1")
            # A pure deletion (count 0) sits between ``start`` and ``start + 1``.
            span = range(start, start + count) if count else range(start, start + 2)
            lines[current].update(span)
    return sorted(set(changed)), sorted(set(deleted)), lines


# ----------------------------------------------------------- source modelling


def _parse(repo: Path, path: str) -> ast.Module | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse((repo / path).read_bytes(), filename=path)
    except (SyntaxError, ValueError, OSError):
        return None


def _package(path: str) -> str:
    package = _module_name(path)
    return package if path.endswith("__init__.py") else package.rpartition(".")[0]


def _import_bindings(nodes: Iterable[ast.AST], path: str) -> dict[str, str]:
    """Local name -> dotted target (``module`` or ``module.name``)."""
    out: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name
                else:
                    head = alias.name.split(".")[0]
                    out[head] = head
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = _package(path).split(".") if _package(path) else []
                if node.level > 1:
                    anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join([*anchor, base] if base else anchor)
            for alias in node.names:
                if alias.name != "*":
                    out[alias.asname or alias.name] = f"{base}.{alias.name}" if base else alias.name
    return out


@dataclass
class Func:
    file: str
    name: str
    start: int
    end: int
    node: ast.AST


@dataclass
class SourceFile:
    path: str
    tree: ast.Module
    bindings: dict[str, str]
    functions: dict[str, Func] = field(default_factory=dict)
    classes: dict[str, ast.ClassDef] = field(default_factory=dict)


def _start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", None) or []
    return min([node.lineno, *(d.lineno for d in decorators)])  # type: ignore[attr-defined]


def _load(repo: Path, path: str, cache: dict[str, SourceFile | None]) -> SourceFile | None:
    if path in cache:
        return cache[path]
    tree = _parse(repo, path)
    if tree is None:
        cache[path] = None
        return None
    src = SourceFile(path, tree, _import_bindings(tree.body, path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            src.functions[node.name] = Func(
                path, node.name, _start(node), node.end_lineno or node.lineno, node
            )
        elif isinstance(node, ast.ClassDef):
            src.classes[node.name] = node
    cache[path] = src
    return src


def _dotted(node: ast.AST) -> list[str] | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return [node.id, *reversed(parts)]
    return None


# ------------------------------------------------------------ Gateway model


@dataclass
class ToolReach:
    funcs: set[tuple[str, str]] = field(default_factory=set)  # (file, qualified name)
    ranges: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    deps: set[str] = field(default_factory=set)

    def add_range(self, path: str, start: int, end: int) -> None:
        self.ranges.setdefault(path, []).append((start, end))


class GatewayModel:
    def __init__(self, repo: Path, modules: Mapping[str, str]) -> None:
        self.repo, self.modules = repo, modules
        self.cache: dict[str, SourceFile | None] = {}
        self.unresolved: list[str] = []
        self.methods: dict[str, Func] = {}  # MRO-first method name -> Func
        self.method_bindings: dict[str, dict[str, str]] = {}
        self.host_files: set[str] = set()
        self.tools: dict[str, ToolReach] = {}
        self.ok = False
        gateway = _load(repo, GATEWAY_FILE, self.cache)
        if gateway is None or GATEWAY_CLASS not in gateway.classes:
            self.unresolved.append(f"{GATEWAY_FILE}: {GATEWAY_CLASS} not found")
            return
        self._collect_class(gateway, GATEWAY_CLASS, set())
        self._collect_tools(gateway)
        self.ok = True

    # -- resolution helpers
    def _resolve_file(self, dotted: str) -> str | None:
        return _resolve(dotted, self.modules)

    def _resolve_symbol(self, dotted: str) -> tuple[str | None, str | None]:
        """(file, top-level name inside it or None when the target is a module)."""
        path = self._resolve_file(dotted)
        if path is None:
            return None, None
        module = _module_name(path)
        rest = dotted[len(module) + 1 :] if dotted.startswith(module + ".") else ""
        return path, (rest.split(".")[0] if rest else None)

    def _collect_class(self, src: SourceFile, name: str, seen: set[tuple[str, str]]) -> None:
        if (src.path, name) in seen:
            return
        seen.add((src.path, name))
        node = src.classes[name]
        self.host_files.add(src.path)
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = Func(
                    src.path,
                    f"{name}.{member.name}",
                    _start(member),
                    member.end_lineno or member.lineno,
                    member,
                )
                self.methods.setdefault(member.name, func)
                self.method_bindings.setdefault(member.name, src.bindings)
        for base in node.bases:
            dotted = _dotted(base)
            if not dotted:
                continue
            if dotted[0] in src.classes and len(dotted) == 1:
                self._collect_class(src, dotted[0], seen)
                continue
            target = src.bindings.get(dotted[0])
            if target is None:
                continue
            path, symbol = self._resolve_symbol(".".join([target, *dotted[1:]]))
            base_src = _load(self.repo, path, self.cache) if path else None
            if base_src is not None and symbol in base_src.classes:
                self._collect_class(base_src, symbol, seen)

    def _string_constant(self, src: SourceFile, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            for stmt in src.tree.body:
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == node.id for t in stmt.targets
                ):
                    return self._string_constant(src, stmt.value)
            target = src.bindings.get(node.id)
            if target:
                path, symbol = self._resolve_symbol(target)
                other = _load(self.repo, path, self.cache) if path else None
                if other is not None and symbol and other is not src:
                    return self._string_constant(other, ast.Name(id=symbol))
        return None

    def _collect_tools(self, gateway: SourceFile) -> None:
        spec = self.methods.get("tool_specs")
        call = self.methods.get("_call_tool")
        if spec is None or call is None:
            self.unresolved.append(f"{GATEWAY_CLASS}: tool_specs or _call_tool not found")
            return
        names: dict[str, tuple[int, int]] = {}
        for node in ast.walk(spec.node):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "name":
                    tool = self._string_constant(gateway, value)
                    if tool:
                        names.setdefault(tool, (node.lineno, node.end_lineno or node.lineno))
        branches: dict[str, ast.If] = {}
        for node in ast.walk(call.node):
            if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
                continue
            test = node.test
            if (
                isinstance(test.left, ast.Name)
                and test.left.id == "name"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
            ):
                src = _load(self.repo, call.file, self.cache)
                tool = self._string_constant(src, test.comparators[0]) if src else None
                if tool is None:
                    self.unresolved.append(f"_call_tool branch at line {node.lineno}")
                else:
                    branches.setdefault(tool, node)
        for tool in sorted(names):
            reach = ToolReach()
            reach.add_range(spec.file, *names[tool])
            branch = branches.get(tool)
            if branch is None:
                self.unresolved.append(f"gateway:{tool}: no _call_tool branch")
            else:
                # The branch is its test and body only: in an if/elif chain the
                # ``orelse`` holds the next tools' branches and must not count.
                end = max(stmt.end_lineno or stmt.lineno for stmt in branch.body)
                reach.add_range(call.file, branch.lineno, end)
                bindings = self.method_bindings.get("_call_tool", {})
                body = ast.Module(body=list(branch.body), type_ignores=[])
                self._walk(body, call.file, bindings, reach)
            self.tools[tool] = reach

    def _walk(
        self, node: ast.AST, path: str, bindings: Mapping[str, str], reach: ToolReach
    ) -> None:
        """Follow self.<method>, same-file functions and imported names from ``node``."""
        pending: deque[tuple[ast.AST, str, Mapping[str, str]]] = deque([(node, path, bindings)])
        while pending:
            current, file, outer = pending.popleft()
            src = _load(self.repo, file, self.cache)
            local = {**outer, **_import_bindings(ast.walk(current), file)}
            for sub in ast.walk(current):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "self"
                ):
                    func = self.methods.get(sub.attr)
                    if func and (func.file, func.name) not in reach.funcs:
                        reach.funcs.add((func.file, func.name))
                        reach.add_range(func.file, func.start, func.end)
                        pending.append((
                            func.node,
                            func.file,
                            self.method_bindings.get(sub.attr, {}),
                        ))
                    continue
                if not isinstance(sub, (ast.Name, ast.Attribute)):
                    continue
                dotted = _dotted(sub)
                if not dotted:
                    continue
                head = dotted[0]
                if src is not None and head in src.functions and head not in local:
                    func = src.functions[head]
                    if (func.file, func.name) not in reach.funcs:
                        reach.funcs.add((func.file, func.name))
                        reach.add_range(func.file, func.start, func.end)
                        pending.append((func.node, func.file, src.bindings))
                    continue
                target = local.get(head)
                if target is None:
                    continue
                target_path, symbol = self._resolve_symbol(".".join([target, *dotted[1:]]))
                if target_path is None:
                    continue
                if target_path in self.host_files:
                    host = _load(self.repo, target_path, self.cache)
                    if host is None or not symbol:
                        continue
                    func = host.functions.get(symbol)
                    if func and (func.file, func.name) not in reach.funcs:
                        reach.funcs.add((func.file, func.name))
                        reach.add_range(func.file, func.start, func.end)
                        pending.append((func.node, func.file, host.bindings))
                else:
                    reach.deps.add(target_path)


# ------------------------------------------------------------------ analysis


def _closure(
    start: Iterable[str], adjacency: Mapping[str, set[str]], stop: AbstractSet[str] = frozenset()
) -> set[str]:
    seen = set(start)
    queue = deque(seen)
    while queue:
        node = queue.popleft()
        if node in stop:
            continue
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _is_extensionless(path: str) -> bool:
    try:
        name = Path(path).name
    except ValueError:
        return False
    return bool(name) and "." not in name


# env(1) options whose value is the next word (macOS and GNU coreutils).
_ENV_OPTIONS_WITH_ARGUMENT = frozenset({"-u", "--unset", "-C", "--chdir", "-P", "-a", "--argv0"})
_PYTHON_INTERPRETER = re.compile(r"python(?:\d+(?:\.\d+)*)?")


def _has_python_shebang(repo: Path, path: str) -> bool:
    """True when ``path`` is a regular file whose ``#!`` interpreter is Python.

    Only the interpreter counts (``#!/usr/bin/env bash python`` is bash); ``env``
    options and ``NAME=value`` assignments before the command are skipped."""
    target = repo / path
    if target.is_symlink() or not target.is_file():
        return False
    try:
        with target.open("rb") as f:
            first_line = f.readline(1024)
    except (OSError, ValueError):
        return False
    if not first_line.startswith(b"#!"):
        return False
    parts = first_line[2:].decode("utf-8", errors="replace").split()
    if parts and PurePosixPath(parts[0]).name == "env":
        parts = parts[1:]
        while parts and (parts[0].startswith("-") or "=" in parts[0]):
            option = parts.pop(0)
            if option in _ENV_OPTIONS_WITH_ARGUMENT and parts:
                parts.pop(0)
    return bool(parts) and _PYTHON_INTERPRETER.fullmatch(PurePosixPath(parts[0]).name) is not None


def _has_main_block(repo: Path, path: str) -> bool:
    tree = _parse(repo, path)
    if tree is None:
        return False
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            consts = {n.value for n in ast.walk(node.test) if isinstance(n, ast.Constant)}
            if "__name__" in names and "__main__" in consts:
                return True
    return False


def _workflow_scripts(
    repo: Path, modules: Mapping[str, str], tracked: set[str]
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    directory = repo / WORKFLOW_DIR
    if not directory.is_dir():
        return out
    for wf in sorted(directory.iterdir()):
        if wf.suffix not in (".yml", ".yaml"):
            continue
        text = wf.read_text(encoding="utf-8", errors="replace")
        rel = f"{WORKFLOW_DIR}{wf.name}"
        hits = {p for p in _PY_PATH.findall(text) if p in tracked}
        for module in _PY_MODULE.findall(text):
            path = modules.get(module)
            if path:
                hits.add(path)
        out[rel] = hits
    return out


def _console_scripts(repo: Path, modules: Mapping[str, str]) -> dict[str, str]:
    try:
        data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out = {}
    for name, target in ((data.get("project") or {}).get("scripts") or {}).items():
        module = str(target).split(":")[0]
        path = modules.get(module)
        if path:
            out[name] = path
    return out


def _launchd(repo: Path, path: str) -> dict[str, list[str]]:
    try:
        data = json.loads((repo / path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EntrypointsError(f"launchd map unreadable: {path}") from exc
    if not isinstance(data, dict) or data.get("schema") != "nexus.launchd_entrypoints.v1":
        raise EntrypointsError(f"launchd map malformed: {path}")
    labels = data.get("labels")
    if not isinstance(labels, dict):
        raise EntrypointsError(f"launchd map malformed: {path}")
    out: dict[str, list[str]] = {}
    for label, entry in labels.items():
        scripts = entry.get("scripts") if isinstance(entry, dict) else None
        if not isinstance(scripts, list) or not all(isinstance(x, str) for x in scripts):
            raise EntrypointsError(f"launchd map malformed at {label!r}: {path}")
        out[label] = list(scripts)
    return out


def _in_ranges(lines: Iterable[int], ranges: Sequence[tuple[int, int]]) -> bool:
    return any(start <= line <= end for line in lines for start, end in ranges)


def analyze(
    repo: Path,
    changed: Sequence[str],
    *,
    changed_lines: Mapping[str, Iterable[int]] | None = None,
    deleted: Sequence[str] = (),
    launchd_map: str = LAUNCHD_MAP,
    files: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Entry points reachable from ``changed`` (paths at the checked-out head)."""
    paths, edge_rows, errors = build_import_graph(repo, files)
    tracked = set(paths)
    modules = {_module_name(p): p for p in paths if _module_name(p)}
    forward: dict[str, set[str]] = {}
    reverse: dict[str, set[str]] = {}
    for edge in edge_rows:
        forward.setdefault(edge["consumer"], set()).add(edge["dependency"])
        reverse.setdefault(edge["dependency"], set()).add(edge["consumer"])
    line_map = {p: set(v) for p, v in (changed_lines or {}).items()}
    changed_py = sorted(p for p in changed if p in tracked)
    entries: dict[str, dict[str, Any]] = {}

    def hit(eid: str, kind: str, via: Iterable[str], why: str) -> None:
        row = entries.setdefault(eid, {"id": eid, "kind": kind, "via": set(), "why": set()})
        row["via"].update(via)
        row["why"].add(why)

    # Reverse closure: every file that can import a changed file, per changed file.
    reached_by: dict[str, set[str]] = {}
    for path in changed_py:
        for consumer in _closure([path], reverse):
            reached_by.setdefault(consumer, set()).add(path)

    gateway = GatewayModel(repo, modules)
    if gateway.ok:
        hosts = gateway.host_files
        attributed: set[str] = set()
        for tool, reach in sorted(gateway.tools.items()):
            closure = _closure(reach.deps, forward, stop=hosts) - hosts
            via = {p for p in changed_py if p not in hosts and p in closure}
            for host, ranges in reach.ranges.items():
                if host in changed and (host not in line_map or _in_ranges(line_map[host], ranges)):
                    via.add(host)
            if via:
                hit(f"gateway:{tool}", "gateway", via, "handler reaches changed code")
                attributed |= via
        # Host-file lines no tool reaches, and changed files only the Gateway module reaches.
        loose: set[str] = set()
        for host in sorted(hosts & set(changed)):
            if host not in line_map:
                continue
            reached_lines = [
                r for reach in gateway.tools.values() for r in reach.ranges.get(host, [])
            ]
            if any(not _in_ranges([line], reached_lines) for line in line_map[host]):
                loose.add(host)
        for path in changed_py:
            if path in attributed or path in hosts:
                continue
            if any(h in _closure([path], reverse) for h in hosts):
                loose.add(path)
        if loose:
            hit(
                "gateway:*",
                "gateway",
                loose,
                "Gateway process reaches it; no single tool attributed",
            )

    for name, path in sorted(_console_scripts(repo, modules).items()):
        if path in reached_by:
            hit(f"console:{name}", "console", reached_by[path], f"[project.scripts] {name}")

    for workflow, scripts in sorted(_workflow_scripts(repo, modules, tracked).items()):
        if workflow in changed:
            hit(f"workflow:{workflow}", "workflow", [workflow], "workflow file changed")
        for script in sorted(scripts):
            if script in reached_by:
                hit(f"workflow:{workflow}", "workflow", reached_by[script], f"runs {script}")

    for label, scripts in sorted(_launchd(repo, launchd_map).items()):
        for script in scripts:
            if script in reached_by:
                hit(f"launchd:{label}", "launchd", reached_by[script], f"runs {script}")

    for path in changed_py:
        if _has_main_block(repo, path):
            hit(
                f"script:{path}",
                "script",
                [path],
                "changed __main__ script: a real run is required",
            )

    for path in sorted(changed):
        if (
            _is_extensionless(path)
            and _has_python_shebang(repo, path)
            and _has_main_block(repo, path)
        ):
            hit(
                f"script:{path}",
                "script",
                [path],
                "changed __main__ script: a real run is required",
            )

    rows = []
    for eid in sorted(entries):
        row = entries[eid]
        via = sorted(row["via"])
        rows.append({
            "id": eid,
            "kind": row["kind"],
            "why": sorted(row["why"]),
            "via": via[:MAX_VIA],
            "via_total": len(via),
        })
    return {
        "schema": SCHEMA,
        "changed_files": sorted(changed),
        "deleted_files": sorted(deleted),
        "entrypoints": rows,
        "unresolved": sorted(set(gateway.unresolved)),
        "gateway_tools_known": len(gateway.tools),
        "graph": {"files": len(paths), "edges": len(edge_rows), "parse_errors": len(errors)},
        "limitations": list(LIMITATIONS),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--repo-root", default=".", help="checkout at --head (default: cwd)")
    ap.add_argument("--base", help="base commit; changed files come from git diff base..head")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument(
        "--changed-file", action="append", default=[], help="explicit changed path (repeatable)"
    )
    ap.add_argument("--launchd-map", default=LAUNCHD_MAP)
    ap.add_argument("--output", help="write JSON here instead of stdout")
    args = ap.parse_args(argv)
    repo = Path(args.repo_root).resolve()
    head = None
    try:
        if args.base:
            head = _git(repo, "rev-parse", args.head).strip()
            checked_out = _git(repo, "rev-parse", "HEAD").strip()
            if head != checked_out:
                raise EntrypointsError("--repo-root must be checked out at --head")
            changed, deleted, lines = changes_from_git(repo, args.base, head)
            changed = sorted(set(changed) | set(args.changed_file))
        elif args.changed_file:
            changed, deleted, lines = sorted(set(args.changed_file)), [], {}
        else:
            ap.error("give --base or --changed-file")
        report = analyze(
            repo, changed, changed_lines=lines, deleted=deleted, launchd_map=args.launchd_map
        )
        if args.base:
            report["base"], report["head"] = args.base, head
    except EntrypointsError as exc:
        print(f"entrypoints_touched: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
