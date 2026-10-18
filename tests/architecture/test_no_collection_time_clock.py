"""No clock reads while pytest collects tests.

Values inside ``pytest.mark.parametrize(...)`` and ``pytest.fixture(params=...)``
are evaluated when the module is collected. In the nightly full regression
(about 28k tests, roughly 1 h 40 min) a test can run an hour or more after
collection, so a timestamp such as ``datetime.now() + timedelta(minutes=5)``
built there silently drifts out of the window the test meant to probe. That is
how #2565 turned the nightly red (#2581, fixed in #2590).

Allowed: compute the time inside the test body, or defer it with a ``lambda``,
a nested ``def`` or a factory (``functools.partial``) that the test calls at
run time. This check flags clock calls that run at collection: directly in the
parametrize / fixture-params expression, through a module-level name that
expression references, or through a module-level helper function that reads
the clock (for example ``def _now(): return datetime.now(...)``).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"

# Attribute calls that read the wall clock whatever the receiver is
# (datetime.now(), datetime.datetime.utcnow(), date.today(), pd.Timestamp.now()).
_CLOCK_ATTRS_ANY_RECEIVER = frozenset({"now", "utcnow", "today"})
# Functions of the ``time`` module.
_TIME_MODULE_FUNCS = frozenset(
    {"time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns"}
)


def _is_parametrize_call(node: ast.Call) -> bool:
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr == "parametrize"


def _fixture_params(node: ast.Call) -> list[ast.expr]:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name != "fixture":
        return []
    return [kw.value for kw in node.keywords if kw.arg == "params"]


def _walk_eager(node: ast.AST) -> Iterator[ast.AST]:
    """Walk an expression, skipping code whose evaluation is deferred."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield from _walk_eager(child)


class _ModuleClock:
    def __init__(self, tree: ast.Module) -> None:
        self.time_names: set[str] = set()  # bare names bound to time-module clocks
        self.time_modules: set[str] = {"time"}  # aliases of the time module
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "time":
                for alias in node.names:
                    if alias.name in _TIME_MODULE_FUNCS:
                        self.time_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "time":
                        self.time_modules.add(alias.asname or "time")
        self.assignments: dict[str, list[ast.expr]] = {}
        functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        self.assignments.setdefault(target.id, []).append(stmt.value)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                if isinstance(stmt.target, ast.Name):
                    self.assignments.setdefault(stmt.target.id, []).append(stmt.value)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions[stmt.name] = stmt
        # Module-level helpers that read the clock when called, resolved to a fixpoint.
        self.clock_helpers: set[str] = set()
        changed = True
        while changed:
            changed = False
            for name, func in functions.items():
                if name in self.clock_helpers:
                    continue
                if any(
                    isinstance(sub, ast.Call) and self.is_clock_call(sub)
                    for stmt in func.body
                    for sub in ast.walk(stmt)
                ):
                    self.clock_helpers.add(name)
                    changed = True

    def is_clock_call(self, call: ast.Call) -> bool:
        func = call.func
        if isinstance(func, ast.Attribute):
            if func.attr in _CLOCK_ATTRS_ANY_RECEIVER:
                return True
            return (
                func.attr in _TIME_MODULE_FUNCS
                and isinstance(func.value, ast.Name)
                and func.value.id in self.time_modules
            )
        if isinstance(func, ast.Name):
            return func.id in self.time_names or func.id in self.clock_helpers
        return False

    def eager_clock_calls(self, expr: ast.expr) -> Iterator[ast.Call]:
        seen: set[str] = set()
        pending: list[ast.expr] = [expr]
        while pending:
            current = pending.pop()
            for node in _walk_eager(current):
                if isinstance(node, ast.Call) and self.is_clock_call(node):
                    yield node
                elif (
                    isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Load)
                    and node.id in self.assignments
                    and node.id not in seen
                ):
                    seen.add(node.id)
                    pending.extend(self.assignments[node.id])


def collection_time_clock_calls(source: str, filename: str = "<string>") -> list[str]:
    """Return ``file:line expr`` for each clock read evaluated at collection."""
    tree = ast.parse(source, filename=filename)
    clock = _ModuleClock(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        exprs: list[ast.expr] = []
        if _is_parametrize_call(node):
            exprs.extend(node.args[1:])
            exprs.extend(kw.value for kw in node.keywords if kw.arg in {"argvalues", "ids"})
        exprs.extend(_fixture_params(node))
        for expr in exprs:
            for call in clock.eager_clock_calls(expr):
                findings.append(f"{filename}:{call.lineno} {ast.unparse(call)}")
    return sorted(set(findings))


def _test_sources(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_no_clock_read_at_collection_time_under_tests() -> None:
    findings: list[str] = []
    for path in _test_sources(TESTS_ROOT):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            findings.extend(collection_time_clock_calls(source, str(path.relative_to(REPO_ROOT))))
        except SyntaxError:
            continue  # fixture files that are deliberately not valid Python
    assert findings == [], (
        "clock read while pytest collects (build the time inside the test, or defer it "
        "with a lambda/factory; see #2581):\n" + "\n".join(findings)
    )


# --- the detector itself --------------------------------------------------------------

_PRE_2590 = """
from datetime import datetime, timedelta, timezone
import pytest

def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)

@pytest.mark.parametrize(
    ("overrides", "message"),
    [({"issuedAt": (_now() + timedelta(minutes=5)).isoformat()}, "FUTURE")],
)
def test_x(overrides, message):
    pass
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_PRE_2590, ["t.py:10 _now()"]),
        (
            "import time, pytest\n"
            "@pytest.mark.parametrize('t', [time.time() + 5])\n"
            "def test_x(t): pass\n",
            ["t.py:2 time.time()"],
        ),
        (
            "from time import monotonic as mono\nimport pytest\n"
            "@pytest.fixture(params=[mono()])\n"
            "def f(request): return request.param\n",
            ["t.py:3 mono()"],
        ),
        (
            "import datetime, pytest\n"
            "CASES = [datetime.datetime.utcnow()]\n"
            "@pytest.mark.parametrize('c', CASES)\n"
            "def test_x(c): pass\n",
            ["t.py:2 datetime.datetime.utcnow()"],
        ),
        (
            "import datetime, pytest\n"
            "parametrize = pytest.mark.parametrize\n"
            "pytestmark = pytest.mark.parametrize('d', [datetime.date.today()])\n"
            "def test_x(d): pass\n",
            ["t.py:3 datetime.date.today()"],
        ),
    ],
    ids=["pre-2590-helper", "time-time", "fixture-params-alias", "module-constant", "pytestmark"],
)
def test_detector_flags_collection_time_clock_reads(source, expected) -> None:
    assert collection_time_clock_calls(source, "t.py") == expected


@pytest.mark.parametrize(
    "source",
    [
        # deferred with lambda / partial / factory: evaluated at run time
        "import functools, datetime, pytest\n"
        "def _build(): return datetime.datetime.now()\n"
        "@pytest.mark.parametrize('f', [lambda: datetime.datetime.now(), "
        "functools.partial(_build)])\n"
        "def test_x(f): f()\n",
        # clock read inside the test body
        "import datetime, pytest\n"
        "@pytest.mark.parametrize('minutes', [5, -31])\n"
        "def test_x(minutes): datetime.datetime.now()\n",
        # fixed timestamps are fine
        "import datetime, pytest\n"
        "@pytest.mark.parametrize('t', [datetime.datetime(2026, 10, 17)])\n"
        "def test_x(t): pass\n",
        # an unrelated .time attribute on a non-time object is not a clock
        "import pytest\n"
        "@pytest.mark.parametrize('t', [obj.time() for obj in []])\n"
        "def test_x(t): pass\n",
    ],
    ids=["deferred", "in-body", "fixed-literal", "non-time-receiver"],
)
def test_detector_allows_run_time_clock_reads(source) -> None:
    assert collection_time_clock_calls(source, "t.py") == []
