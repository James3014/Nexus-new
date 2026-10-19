#!/usr/bin/env python3
"""
Policy Lane Gate — 分級治理 gate checker.

Usage:
    python scripts/ops/check_policy_lane_gate.py --policy-id P-GATE-03 --action modify
    python scripts/ops/check_policy_lane_gate.py --policy-id P-ROUTE-01 --action modify
    python scripts/ops/check_policy_lane_gate.py --policy-id P-AUTO-01 --action observe
"""

import argparse
import ast
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docs" / "reports" / "policy-manifest.v2.json"
OVERRIDE_DIR = REPO_ROOT / ".nexus" / "policy_overrides"

# #2259: how a policy acts in production. ``block`` stops or alters execution,
# ``record_only`` records a signal and never blocks, ``not_wired`` has no
# production caller (fixture or spec-only entry).
ENFORCEMENT_MODES = ("block", "record_only", "not_wired")
# How far the static import walk follows repo modules from a test entrypoint
# before giving up (test -> helper -> re-export shim -> production caller).
_IMPORT_WALK_DEPTH = 3


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text())


def find_policy(manifest: dict, policy_id: str) -> dict | None:
    for p in manifest.get("policies", []):
        if p["policy_id"] == policy_id:
            return p
    return None


def _source_paths(policy: dict) -> list[str]:
    """``source_file`` is one path or a ``;``-separated list of paths."""
    raw = str(policy.get("source_file") or "")
    return [part.strip() for part in raw.split(";") if part.strip()]


def _module_name(path: str) -> str | None:
    """Repo-relative ``.py`` path -> dotted module name (None for non-Python)."""
    if not path.endswith(".py"):
        return None
    parts = Path(path).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _contained(path: Path, repo_root: Path) -> Path | None:
    """``path`` resolved, only if it stays inside ``repo_root`` (symlinks followed)."""
    try:
        resolved = path.resolve()
        resolved.relative_to(repo_root.resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved


def _module_file(module: str, repo_root: Path) -> Path | None:
    parts = module.split(".")
    if not module or any(not part or part in (".", "..") for part in parts):
        return None
    base = repo_root.joinpath(*parts)
    # Python resolves a regular package before a same-named module.
    for candidate in (base / "__init__.py", base.with_suffix(".py")):
        resolved = _contained(candidate, repo_root)
        if resolved is not None and resolved.is_file():
            return resolved
    return None


def _is_type_checking_guard(node: ast.AST) -> bool:
    """``if TYPE_CHECKING:`` / ``if typing.TYPE_CHECKING:`` — imports there never run."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _package_parts(path: Path, repo_root: Path) -> list[str]:
    """Dotted-path components of the package that ``path`` belongs to."""
    try:
        parts = list(path.resolve().relative_to(repo_root.resolve()).with_suffix("").parts)
    except (OSError, ValueError, RuntimeError):
        return []
    if parts and parts[-1] == "__init__":
        parts.pop()
        return parts
    return parts[:-1]


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return None


def _module_level(tree: ast.Module) -> list[ast.AST]:
    """Top-level statements of a module that are not def/class bodies (kept whole)."""
    return [node for node in tree.body if not isinstance(node, _DEFS)]


def _class_level(node: ast.ClassDef) -> list[ast.AST]:
    """Statements in a class body that are not nested defs (``self.x`` imports, etc.)."""
    return [child for child in node.body if not isinstance(child, _DEFS)]


def _branch_state(node: ast.If) -> str:
    """``dead`` (body never runs), ``live`` (body always runs, else never), or ``unknown``.

    ``if TYPE_CHECKING:`` / ``if False:`` / ``if 0:`` are dead; ``if not
    TYPE_CHECKING:`` / ``if True:`` / ``if 1:`` are live. Anything else is walked
    on both sides.
    """
    test = node.test
    if _is_type_checking_guard(node):
        return "dead"
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = ast.If(test=test.operand, body=[], orelse=[])
        if _is_type_checking_guard(inner):
            return "live"
        if isinstance(test.operand, ast.Constant):
            return "live" if not test.operand.value else "dead"
    if isinstance(test, ast.Constant):
        return "live" if test.value else "dead"
    return "unknown"


def _imports_in(nodes: list[ast.AST], package: list[str], *, into_defs: bool) -> set[str]:
    """Absolute module names imported by ``nodes`` (static, ``ast`` only).

    Relative imports are resolved against ``package``. ``importlib`` / string
    imports are not seen (the walk fails closed); a branch that provably never
    runs (``if TYPE_CHECKING:``, ``if False:``, the ``else`` of ``if not
    TYPE_CHECKING:``) is ignored. With ``into_defs`` False the walk does not
    enter def/class bodies it meets (used for the module-level view of a
    selected test).
    """
    found: set[str] = set()

    def push(children: list[ast.AST] | list[ast.stmt]) -> None:
        for child in children:
            if into_defs or not isinstance(child, _DEFS):
                stack.append(child)

    stack: list[ast.AST] = []
    push(list(nodes))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.If):
            state = _branch_state(node)
            if state == "dead":
                push(node.orelse)
                continue
            if state == "live":
                push(node.body)
                continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 >= len(package):
                    continue
                base = package[: len(package) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module:
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
        push(list(ast.iter_child_nodes(node)))
    return found


def _visible_imports(tree: ast.Module, chain: list[ast.AST], package: list[str]) -> set[str]:
    """Imports one resolved test chain ``[TestClass, ..., test_function]`` can see."""
    visible: list[ast.AST] = list(_module_level(tree))
    for node in chain[:-1]:
        if isinstance(node, ast.ClassDef):
            visible.extend(_class_level(node))
    found = _imports_in(visible, package, into_defs=False)
    # The test's own body, but not functions nested inside it: a nested helper
    # that the test never calls must not count either.
    found |= _imports_in(list(ast.iter_child_nodes(chain[-1])), package, into_defs=False)
    return found


def _imported_modules(
    path: Path,
    repo_root: Path,
    selected: list[ast.AST] | None = None,
    *,
    entrypoint: bool = False,
) -> set[str]:
    """Modules visible from ``path``.

    For the entrypoint file: ``selected`` is the resolved chain ``[TestClass,
    ..., test_function]``; the test sees the module-level statements, the
    non-def statements of each enclosing class, and its own body. Imports made
    inside other functions, helpers or fixtures of the same file do not count
    for it (fail closed). A whole-file entry (``selected`` None) is the union
    over its collectable tests, so an unused helper's import does not count
    either. Any module the walk reaches afterwards (``entrypoint`` False) is
    scanned whole, whatever its name.
    """
    tree = _parse(path)
    if tree is None:
        return set()
    package = _package_parts(path, repo_root)
    if selected is not None:
        return _visible_imports(tree, selected, package)
    if not entrypoint:
        return _imports_in([tree], package, into_defs=True)
    found: set[str] = set()
    for chain in _collectable_chains(list(tree.body), _fixture_bindings(tree)):
        found |= _visible_imports(tree, chain, package)
    return found


_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_DRILLED = re.compile(r"drilled-[0-9]{4}-[0-9]{2}-[0-9]{2}")
# pytest.ini: python_classes = Test*, python_functions = test_*
_TEST_FUNCTION_PREFIX = "test_"
_TEST_CLASS_PREFIX = "Test"
_PYTEST_MODULES = ("pytest", "_pytest.fixtures", "pytest_asyncio")


def _is_drilled(status: Any) -> bool:
    """Exactly ``drilled-YYYY-MM-DD`` with a real calendar date; nothing else counts."""
    text = status if isinstance(status, str) else ""
    if _DRILLED.fullmatch(text) is None:
        return False
    try:
        date.fromisoformat(text[len("drilled-") :])
    except ValueError:
        return False
    return True


def _fixture_bindings(tree: ast.Module) -> tuple[set[str], set[str]]:
    """(names bound to pytest's ``fixture``, names bound to a pytest module), module level.

    Covers ``from pytest import fixture [as fx]`` / ``*``, ``from _pytest.fixtures
    import fixture``, ``import pytest [as pt]``, ``import pytest_asyncio``, and
    simple, tuple or annotated assignments ``fx = pytest.fixture`` / ``pt = pytest``.
    Only module-level statements count: a binding inside a function cannot
    decorate a module-level test. Dynamic aliases (``getattr``) are outside a
    static check.
    """
    fixtures: set[str] = set()
    modules: set[str] = set()
    nodes = _module_level(tree)

    def pairs(node: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            return [(node.target, node.value)]
        if not isinstance(node, ast.Assign):
            return []
        out: list[tuple[ast.AST, ast.AST]] = []
        for target in node.targets:
            if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                out.extend(zip(target.elts, node.value.elts))
            else:
                out.append((target, node.value))
        return out

    changed = True
    while changed:
        changed = False
        for node in nodes:
            if isinstance(node, ast.ImportFrom) and node.module in _PYTEST_MODULES:
                for alias in node.names:
                    if alias.name in ("fixture", "*"):
                        bound = alias.asname or "fixture"
                        if bound not in fixtures:
                            fixtures.add(bound)
                            changed = True
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _PYTEST_MODULES:
                        bound = alias.asname or alias.name.split(".", 1)[0]
                        if bound not in modules:
                            modules.add(bound)
                            changed = True
            for target, value in pairs(node):
                if not isinstance(target, ast.Name):
                    continue
                is_fixture = (isinstance(value, ast.Name) and value.id in fixtures) or (
                    isinstance(value, ast.Attribute)
                    and value.attr == "fixture"
                    and isinstance(value.value, ast.Name)
                    and value.value.id in modules
                )
                is_module = isinstance(value, ast.Name) and value.id in modules
                if is_fixture and target.id not in fixtures:
                    fixtures.add(target.id)
                    changed = True
                if is_module and target.id not in modules:
                    modules.add(target.id)
                    changed = True
    return fixtures, modules


def _is_fixture(node: ast.AST, bindings: tuple[set[str], set[str]]) -> bool:
    """``@pytest.fixture`` / ``@fixture`` / ``@fx`` (alias) / ``...(...)`` — not a test.

    Structural match only: ``@Marker.fx`` is not a fixture even when ``fx`` is an
    alias, and ``@other.fixture`` is not unless ``other`` is bound to pytest.
    """
    fixtures, modules = bindings
    for dec in getattr(node, "decorator_list", []):
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id in fixtures:
            return True
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "fixture"
            and isinstance(target.value, ast.Name)
            and target.value.id in modules
        ):
            return True
    return False


def _collectable_chains(
    body: list[ast.stmt], bindings: tuple[set[str], set[str]], prefix: list[ast.AST] | None = None
) -> list[list[ast.AST]]:
    """Every ``test_*`` function in ``body`` (directly or inside ``Test*`` classes), as chains."""
    chains: list[list[ast.AST]] = []
    for node in body:
        if isinstance(node, _FUNCS) and node.name.startswith(_TEST_FUNCTION_PREFIX):
            if not _is_fixture(node, bindings):
                chains.append((prefix or []) + [node])
        elif isinstance(node, ast.ClassDef) and node.name.startswith(_TEST_CLASS_PREFIX):
            chains.extend(_collectable_chains(list(node.body), bindings, (prefix or []) + [node]))
    return chains


def _collectable_tests(body: list[ast.stmt], bindings: tuple[set[str], set[str]]) -> bool:
    """True when ``body`` holds a ``test_*`` function (directly or inside ``Test*`` classes)."""
    return bool(_collectable_chains(body, bindings))


def _resolve_entrypoint(path: Path, selector: str | None) -> list[ast.AST] | None:
    """Resolve ``file::Class::test_name`` the way pytest collects it.

    Returns the chain ``[TestClass, ..., test_function]`` for a selector, ``[]``
    for a whole-file entry (``selector`` is None) that is a ``test_*.py`` file
    holding at least one collectable test, or ``None`` when nothing collectable
    matches. The first component must be a top-level class or function, each
    next component a class directly inside the previous one, and the last a
    plain ``test_*`` function that is not a fixture; classes must be ``Test*``.
    ``file::a::b`` with two unrelated functions, a fixture, a helper such as
    ``_run``, an empty selector, a non-test module as a whole-file entry, or any
    ``[param]`` id are not accepted. Tests defined under ``if``/``try``,
    inherited from a base class, or a whole class ``file::TestA`` are not
    recognised (fail closed).
    """
    tree = _parse(path)
    if tree is None:
        return None
    bindings = _fixture_bindings(tree)
    if selector is None:
        # pytest.ini: python_files = test_*.py
        if not path.name.startswith(_TEST_FUNCTION_PREFIX) or not path.name.endswith(".py"):
            return None
        return [] if _collectable_tests(list(tree.body), bindings) else None
    if "[" in selector or "]" in selector or not selector.strip():
        # Parametrized ids (``test_x[a-b]``) cannot be resolved statically: pytest
        # derives them from values, fixtures and ``ids=``. List the function instead.
        return None
    names = [part.strip() for part in selector.split("::")]
    if any(not name for name in names):
        return None
    body: list[ast.stmt] = list(tree.body)
    chain: list[ast.AST] = []
    for index, name in enumerate(names):
        last = index == len(names) - 1
        kinds = _FUNCS if last else (ast.ClassDef,)
        prefix = _TEST_FUNCTION_PREFIX if last else _TEST_CLASS_PREFIX
        if not name.startswith(prefix):
            return None
        match = next((n for n in body if isinstance(n, kinds) and n.name == name), None)
        if match is None:
            return None
        chain.append(match)
        body = list(match.body)
    if not chain or _is_fixture(chain[-1], bindings):
        return None
    return chain


def _entrypoint_exists(path: Path, selector: str) -> bool:
    """Backwards-compatible boolean form of :func:`_resolve_entrypoint`."""
    return _resolve_entrypoint(path, selector if selector else None) is not None


def _file_id(path: Path) -> tuple[int, int] | None:
    """Physical identity of a file (device, inode); None when it cannot be read."""
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


def _declared_file(path_text: str, root: Path) -> Path | None:
    """The declared repo-relative file, or None when absent / outside the repo."""
    if not path_text or Path(path_text).is_absolute():
        return None
    resolved = _contained(root / path_text, root)
    return resolved if resolved is not None and resolved.is_file() else None


def check_enforcement_wiring(policy: dict, repo_root: Path | None = None) -> list[str]:
    """#2259: a ``block``/``record_only`` policy must be tested through a production caller.

    Static check. Every ``source_file`` and every test entrypoint must exist
    inside the repo. ``source_file`` minus ``guard_modules`` are the production
    callers. At least one Python test entrypoint must reach one of them through
    the static import closure visible to that test (module-level statements,
    enclosing class bodies and its own body; repo modules only, depth-limited;
    never through a guard module). Imports made in same-file helpers or
    fixtures the test calls are not credited (fail closed). A test whose only
    imports are the guard itself proves the guard works, not that anything
    enforces it (#2199).

    Limits, stated plainly: this is an import check, not an execution check. A
    test file whose module-level imports reach a caller passes for every test
    in it. For a single-source policy the guard and the caller are the same
    file, so the check reduces to "a test entrypoint imports the source
    module"; ``guard_modules`` is therefore required whenever ``source_file``
    lists more than one path. Policies whose ``source_file`` has no Python
    module (Rust-only) get the existence checks only, and ``not_wired``
    policies are out of scope.
    """
    root = REPO_ROOT if repo_root is None else repo_root
    mode = policy.get("enforcement_mode")
    if mode not in ENFORCEMENT_MODES:
        return ["ENFORCEMENT_MODE_INVALID"]
    if mode == "not_wired":
        return []
    sources = _source_paths(policy)
    if not sources:
        return ["SOURCE_FILE_MISSING"]
    guards = {str(g).strip() for g in policy.get("guard_modules") or []}
    unknown_guards = sorted(guards - set(sources))
    if unknown_guards:
        return [f"GUARD_MODULE_NOT_IN_SOURCE: {', '.join(unknown_guards)}"]
    if len(sources) > 1 and not guards:
        return ["GUARD_MODULES_REQUIRED"]
    absent_sources = [path for path in sources if _declared_file(path, root) is None]
    if absent_sources:
        return [f"SOURCE_FILE_NOT_FOUND: {', '.join(absent_sources)}"]

    entries = [str(entry) for entry in policy.get("test_entrypoints") or []]
    resolved: list[tuple[str, Path, list[ast.AST] | None]] = []  # (entry, file, chain)
    missing: list[str] = []
    for entry in entries:
        file_part, sep, selector = entry.partition("::")
        file_part = file_part.strip()
        start = _declared_file(file_part, root)
        if start is None:
            missing.append(entry)
            continue
        if not file_part.endswith(".py"):
            continue  # exists; not part of the import walk
        chain = _resolve_entrypoint(start, selector if sep else None)
        if chain is None:
            missing.append(entry)
            continue
        resolved.append((entry, start, chain or None))
    errors: list[str] = []
    if missing:
        # Every listed entrypoint must exist, even when another one reaches a caller.
        errors.append(f"TEST_ENTRYPOINT_NOT_FOUND: {', '.join(missing)}")

    py_sources = {m for m in (_module_name(p) for p in sources) if m}
    if not py_sources:
        return errors
    guard_modules = {m for m in (_module_name(g) for g in guards) if m}
    caller_paths = [p for p in sources if _module_name(p) and _module_name(p) not in guard_modules]
    if not caller_paths:
        return errors + ["ENFORCEMENT_CALLERS_MISSING"]
    # Guards are excluded by module name *and* by file identity (device+inode, so
    # symlinks and hard links to a guard are the guard), and a declared caller that
    # is physically a guard file is not a caller.
    guard_ids: set[tuple[int, int]] = set()
    for guard in guards:
        file = _declared_file(guard, root)
        identity = _file_id(file) if file is not None else None
        if identity is None:
            return errors + [f"SOURCE_FILE_NOT_FOUND: {guard}"]  # unreadable: fail closed
        guard_ids.add(identity)
    caller_paths = [
        path
        for path in caller_paths
        if (f := _declared_file(path, root)) is not None
        and (fid := _file_id(f)) is not None
        and fid not in guard_ids
    ]
    if not caller_paths:
        return errors + ["ENFORCEMENT_CALLERS_MISSING"]
    callers = {m for m in (_module_name(p) for p in caller_paths) if m}
    caller_ids = {i for i in (_file_id(_declared_file(p, root) or root) for p in caller_paths)}
    # A caller inside a guard package can never be reached without loading the
    # guard first; say so instead of failing every entrypoint silently.
    shadowed = sorted(
        path
        for path in caller_paths
        if any(
            ".".join((_module_name(path) or "").split(".")[:depth]) in guard_modules
            for depth in range(1, len((_module_name(path) or "").split(".")))
        )
    )
    if shadowed:
        return errors + [f"CALLER_UNDER_GUARD_PACKAGE: {', '.join(shadowed)}"]
    # The mirror image is refused too: a caller package that contains a guard
    # would let a guard-only test pass (the package runs before the guard), so
    # the manifest must name the concrete caller module instead.
    guard_names = {m for m in (_module_name(g) for g in guards) if m}
    covering = sorted(
        path
        for path in caller_paths
        if path.endswith("__init__.py")
        and any(
            g == (_module_name(path) or "") or g.startswith((_module_name(path) or "") + ".")
            for g in guard_names
        )
    )
    if covering:
        return errors + [f"GUARD_UNDER_CALLER_PACKAGE: {', '.join(covering)}"]

    def _on_disk(path: Path) -> bool:
        """``lstat`` succeeds (dangling symlinks count); an lstat *error* counts as present."""
        try:
            os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return False
        except OSError:
            return True  # unreadable: fail closed
        return True

    def classify(module: str) -> str | None:
        """``"guard"``, ``"caller"`` or None for an import of ``a.b.c``.

        Python loads ``a``, then ``a.b``, then ``a.b.c``, so the prefixes are
        classified shallow to deep and the first guard or caller met decides:
        a guard above a caller means the route goes through the guard; a caller
        package above a guard child means the caller package ran first. A prefix
        whose file exists on disk but cannot be resolved or read is a guard (fail
        closed); a namespace package (nothing on disk) is neither.
        """
        parts = module.split(".")
        for depth in range(1, len(parts) + 1):
            prefix = ".".join(parts[:depth])
            if prefix in guard_modules:
                return "guard"
            base = root.joinpath(*parts[:depth])
            file = _module_file(prefix, root)
            if file is None:
                if (
                    prefix in callers
                    or _on_disk(base.with_suffix(".py"))
                    or _on_disk(base / "__init__.py")
                ):
                    return "guard"  # a declared caller that no longer resolves: fail closed
                continue
            identity = _file_id(file)
            if identity is None or identity in guard_ids:
                return "guard"
            # A caller counts only once its file resolved to a non-guard identity.
            if prefix in callers or identity in caller_ids:
                return "caller"
        return None

    reached = False
    for _entry, start, selected in resolved:
        seen: set[str] = set()
        # Never re-enter the entrypoint file through an import cycle: at depth >= 1
        # it would be scanned whole and credit its unused helpers.
        entry_module = _module_name(start.relative_to(root.resolve()).as_posix())
        if entry_module:
            seen.add(entry_module)
        frontier: list[tuple[Path, list[ast.AST] | None, bool]] = [(start, selected, True)]
        for _ in range(_IMPORT_WALK_DEPTH):
            next_frontier: list[tuple[Path, list[ast.AST] | None, bool]] = []
            for file, node, is_entry in frontier:
                for module in _imported_modules(file, root, node, entrypoint=is_entry):
                    if module in seen:
                        continue
                    seen.add(module)
                    kind = classify(module)
                    if kind == "guard":
                        continue
                    if kind == "caller":
                        reached = True
                        break
                    target = _module_file(module, root)
                    if target is None or target == start:
                        continue
                    next_frontier.append((target, None, False))
                if reached:
                    break
            if reached or not next_frontier:
                break
            frontier = next_frontier
        if reached:
            break
    if not reached:
        errors.append("TEST_ENTRYPOINT_NOT_BEHAVIOURAL")
    return errors


def check_hard_lane(policy: dict, action: str) -> dict:
    """Hard lane: fail-closed. Requires evidence, drill, held-out, feature flag."""
    errors = []

    if action in ("modify", "promote", "cutover"):
        # Only an explicit ``drilled-YYYY-MM-DD`` counts; "no-drill", "", null or any
        # other spelling is missing (#2263 review).
        if not _is_drilled(policy.get("rollback_drill_status")):
            errors.append("ROLLBACK_DRILL_MISSING")
        if not policy.get("test_entrypoints"):
            errors.append("TEST_COVERAGE_MISSING")
        else:
            errors.extend(check_enforcement_wiring(policy))
        if policy.get("enforcement_mode") == "not_wired":
            # A hard-lane policy that enforces nothing cannot be modified under the
            # hard-lane contract; relabelling is not a way around the wiring check.
            errors.append("HARD_LANE_NOT_WIRED")

    if action == "promote":
        if policy.get("promotion_allowed") is False:
            errors.append("PROMOTION_NOT_ALLOWED")

    if action == "cutover":
        errors.append("CUTOVER_REQUIRES_HUMAN_APPROVAL")

    return {
        "allowed": len(errors) == 0,
        "lane": "hard",
        "errors": errors,
        "policy_id": policy["policy_id"],
    }


def check_soft_lane(policy: dict, action: str, override_receipt: dict | None = None) -> dict:
    """Soft lane: versioned changes allowed with manifest record."""
    errors = []

    if action in ("modify", "version_bump"):
        if not policy.get("version_history"):
            errors.append("VERSION_HISTORY_EMPTY")

    if action == "modify" and not override_receipt:
        # Soft lane allows modification without override, but needs version bump
        pass  # allowed

    if override_receipt:
        # Check override validity
        expiry = override_receipt.get("expiry")
        if expiry:
            try:
                expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                if expiry_dt < datetime.now(timezone.utc):
                    errors.append("OVERRIDE_EXPIRED")
            except ValueError:
                errors.append("OVERRIDE_EXPIRY_INVALID")

    return {
        "allowed": len(errors) == 0,
        "lane": "soft",
        "errors": errors,
        "policy_id": policy["policy_id"],
    }


def check_shadow_lane(policy: dict, action: str) -> dict:
    """Shadow lane: observation-only, no authority change."""
    errors = []

    if action in ("modify", "promote", "cutover"):
        if policy.get("authority_impact", "none") != "none":
            errors.append("SHADOW_CANNOT_CHANGE_AUTHORITY")
        if policy.get("claim_impact", "none") not in ("none",):
            errors.append("SHADOW_CANNOT_EXPAND_CLAIM")

    return {
        "allowed": len(errors) == 0,
        "lane": "shadow",
        "errors": errors,
        "policy_id": policy["policy_id"],
    }


def check_lane_gate(policy_id: str, action: str, override_receipt: dict | None = None) -> dict:
    """Main entry point: check if an action is allowed for a policy."""
    manifest = load_manifest()
    policy = find_policy(manifest, policy_id)

    if not policy:
        return {
            "allowed": False,
            "lane": "unknown",
            "errors": [f"POLICY_NOT_FOUND: {policy_id}"],
            "policy_id": policy_id,
        }

    lane = policy.get("lane", "unknown")

    if policy.get("enforcement_mode") not in ENFORCEMENT_MODES:
        # #2259: every entry declares how it enforces; an unreadable entry fails closed.
        return {
            "allowed": False,
            "lane": lane,
            "errors": ["ENFORCEMENT_MODE_INVALID"],
            "policy_id": policy_id,
        }

    if lane == "hard":
        return check_hard_lane(policy, action)
    elif lane == "soft":
        return check_soft_lane(policy, action, override_receipt)
    elif lane == "shadow":
        return check_shadow_lane(policy, action)
    else:
        return {
            "allowed": False,
            "lane": lane,
            "errors": [f"UNKNOWN_LANE: {lane}"],
            "policy_id": policy_id,
        }


def main():
    parser = argparse.ArgumentParser(description="Policy Lane Gate Checker")
    parser.add_argument("--policy-id", required=True, help="Policy ID to check")
    parser.add_argument(
        "--action",
        required=True,
        choices=["modify", "promote", "cutover", "observe", "version_bump"],
    )
    parser.add_argument("--override-receipt", help="Path to override receipt JSON")
    args = parser.parse_args()

    override = None
    if args.override_receipt:
        override = json.loads(Path(args.override_receipt).read_text())

    result = check_lane_gate(args.policy_id, args.action, override)
    print(json.dumps(result, indent=2))

    sys.exit(0 if result["allowed"] else 1)


if __name__ == "__main__":
    main()
