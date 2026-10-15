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
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
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
    """Nodes a module-level test can see: everything outside def/class bodies."""
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _DEFS):
            continue
        out.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return out


def _imports_in(nodes: list[ast.AST], package: list[str]) -> set[str]:
    """Absolute module names imported by ``nodes`` (static, ``ast`` only).

    Relative imports are resolved against ``package``. ``importlib`` / string
    imports are not seen (the walk fails closed) and anything under
    ``if TYPE_CHECKING:`` is ignored because it never executes.
    """
    found: set[str] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            stack.extend(node.orelse)
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
        stack.extend(ast.iter_child_nodes(node))
    return found


def _imported_modules(path: Path, repo_root: Path, selected: ast.AST | None = None) -> set[str]:
    """Modules visible to the selected test (or to the whole file when ``selected`` is None).

    A selected test sees the module-level statements and its own body; imports
    made inside other functions of the same file do not count for it.
    """
    tree = _parse(path)
    if tree is None:
        return set()
    package = _package_parts(path, repo_root)
    if selected is None:
        return _imports_in([tree], package)
    return _imports_in(_module_level(tree) + [selected], package)


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


def _resolve_entrypoint(path: Path, selector: str | None) -> ast.AST | None | bool:
    """Resolve ``file::Class::test_name`` the way pytest collects it.

    Returns the selected function node, ``True`` for a whole-file entry
    (``selector`` is None), or ``False`` when nothing collectable matches. The
    first component must be a top-level class or function, each next component
    a class directly inside the previous one, and the last a plain ``test_*``
    function that is not a fixture; classes must be ``Test*``. ``file::a::b``
    with two unrelated functions, a fixture, a helper such as ``_run``, an
    empty selector, or any ``[param]`` id are not accepted. Tests defined under
    ``if``/``try``, inherited from a base class, or a whole class ``file::TestA``
    are not recognised (fail closed).
    """
    tree = _parse(path)
    if tree is None:
        return False
    if selector is None:
        return True
    if "[" in selector or "]" in selector or not selector.strip():
        # Parametrized ids (``test_x[a-b]``) cannot be resolved statically: pytest
        # derives them from values, fixtures and ``ids=``. List the function instead.
        return False
    names = [part.strip() for part in selector.split("::")]
    if any(not name for name in names):
        return False
    body: list[ast.stmt] = list(tree.body)
    match: ast.stmt | None = None
    for index, name in enumerate(names):
        last = index == len(names) - 1
        kinds = _FUNCS if last else (ast.ClassDef,)
        prefix = _TEST_FUNCTION_PREFIX if last else _TEST_CLASS_PREFIX
        if not name.startswith(prefix):
            return False
        match = next((n for n in body if isinstance(n, kinds) and n.name == name), None)
        if match is None:
            return False
        body = list(match.body)
    if match is None or _is_fixture(match, _fixture_bindings(tree)):
        return False
    return match


def _entrypoint_exists(path: Path, selector: str) -> bool:
    """Backwards-compatible boolean form of :func:`_resolve_entrypoint`."""
    return _resolve_entrypoint(path, selector if selector else None) is not False


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
    the static import closure visible to that test (module-level statements and
    its own body; repo modules only, depth-limited; never through a guard
    module). A test whose only imports are the guard itself proves the guard
    works, not that anything enforces it (#2199).

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
    resolved: list[tuple[str, Path, ast.AST | None]] = []  # (entry, file, selected node)
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
        node = _resolve_entrypoint(start, selector if sep else None)
        if node is False:
            missing.append(entry)
            continue
        resolved.append((entry, start, None if node is True else node))
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
    callers = {m for m in (_module_name(p) for p in caller_paths) if m}

    reached = False
    for _entry, start, selected in resolved:
        seen: set[str] = set()
        frontier: list[tuple[Path, ast.AST | None]] = [(start, selected)]
        for _ in range(_IMPORT_WALK_DEPTH):
            next_frontier: list[tuple[Path, ast.AST | None]] = []
            for file, node in frontier:
                for module in _imported_modules(file, root, node):
                    if module in callers:
                        reached = True
                        break
                    if module in seen or module in guard_modules:
                        continue
                    seen.add(module)
                    target = _module_file(module, root)
                    if target is not None:
                        next_frontier.append((target, None))
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
