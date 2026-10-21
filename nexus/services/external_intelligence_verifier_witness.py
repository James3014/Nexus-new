"""Trusted pytest witness for EIA closure verifiers (#2795).

Closure copies this file into a per-run directory the verifier child cannot write and
loads it with ``-p`` before any candidate code is imported.  It is the child half of the
out-of-process evidence channel; the parent half is
``nexus.services.external_intelligence_closure._witness_outcomes``.

Why a witness and not pytest's own reports: candidate code runs inside the pytest
process.  It can forge a JUnit file, patch ``_pytest.reports`` at import, or register
itself as a plugin (``pytest_plugins`` in a test module) and rewrite every report.  The
parent therefore never trusts a report saying "passed".  A test counts as passed only
when this witness also saw, through ``sys.monitoring``, the test function's own code
object start and finish by returning, never by an exception unwinding out of it.
Rewriting a report, swallowing the exception inside ``Item.runtest`` or a hookwrapper, or
not calling the test at all cannot produce that observation.

The channel:

* the records go to an inherited pipe fd that the parent reads; the child gets no
  writable path for evidence;
* every record carries an HMAC-SHA256 under a per-run key that arrives on a second pipe
  fd, is read once, and is then closed, so bytes written to the pipe by other code are
  rejected as tampering;
* records are numbered; a gap, a bad MAC or a missing final ``end`` record fails closed.

A pass also needs the observed code object to be the test file's own definition: the
parent compares file, qualname and first line with what ``ast`` reads from the checked-out
test file, so swapping the test object (``Function._getobj``, ``obj``, the ``_obj`` cache)
for an in-tree no-op is refused.

pytest's and pluggy's code is fingerprinted by content, not only identity (#2812,
#2815).  The baseline is taken while pytest imports and registers this module for
``-p`` (``Config._preparse``), before ``pytest_load_initial_conftests`` imports any
conftest and so before any candidate code: the witness sweeps every loaded ``pytest``,
``_pytest.*``, ``pluggy.*`` and ``pytest_asyncio`` module: every module-level and class
attribute (read raw from ``__dict__``, so descriptors are not bound) by identity, and
every function behind them by code object, defaults, keyword defaults and closure cell
contents.  It also records every hook caller, its ``_hookexec``, the order of its
hookimpls and each hookimpl's function fingerprint.  A hot subset (the call/report
internals, pluggy's call path, the hook callers and hookimpls) is re-checked around every
test; the full sweep when collection starts (only the exact ``CONFIGURE_TIME_WRITES``
that pytest's own plugins make during configure are re-based there, pinned to pytest's
own values) and at session end.  Any change, a removed or reordered hookimpl, or a later
hookimpl from an untrusted file is ``VERIFIER_PYTEST_INTERNALS_PATCHED``.  So is a
module of those packages first imported after the baseline, or replaced in
``sys.modules`` (#2811): it was never swept, so it fails closed.

The emitter, key and fd are closure cells captured at import, and the module removes
itself from ``sys.modules`` once its plugin is registered, so ``import``-by-name and
attribute patches no longer reach them (#2808 review).

Residual (documented in the PR): this is not a security boundary against a candidate that
knows about the witness.  The plugin and its closure cells stay reachable through the
plugin manager and ``gc``, and closure cells are writable, so a short targeted
monkeypatch can still rewrite the records.  The same holds for other in-process
candidate code: ``CodeType.replace`` on the test function's ``__code__`` keeping its
filename, qualname and first line; jumping ``frame.f_lineno`` from candidate code the
test calls; and plugin trust, which relies on a self-reported module path and on the git
state rather than on the content actually loaded.  So do plugin-instance state (``self``
attributes of a registered plugin object), the fixture manager's internal data, and
mutation inside containers (a dict or list held in a module global or closure cell keeps
its identity).  Witness-targeted and these
in-process routes are out of scope for P1 of #2795; the candidate diff review and the
claim ceiling are the backstop.
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

WITNESS_FD_ENV = "NEXUS_VERIFIER_WITNESS_FD"
WITNESS_KEY_FD_ENV = "NEXUS_VERIFIER_WITNESS_KEY_FD"
WITNESS_KEY_BYTES = 32
WITNESS_TOOL_NAME = "nexus-eia-verifier-witness"
# pytest internals a candidate would patch to rewrite outcomes.  Their identity AND content
# (code object, defaults, keyword defaults, closure cell contents; #2812) are taken at
# ``-p`` import/registration, before conftests load, and compared again when collection
# starts, around every test and at session end.
PYTEST_INTERNALS = (
    ("_pytest.reports", "TestReport"),
    ("_pytest.reports", "TestReport.from_item_and_call"),
    ("_pytest.reports", "CollectReport"),
    ("_pytest.runner", "TestReport"),
    ("_pytest.runner", "CallInfo.from_call"),
    ("_pytest.runner", "call_and_report"),
    ("_pytest.runner", "call_runtest_hook"),
    ("_pytest.runner", "runtestprotocol"),
    ("_pytest.runner", "pytest_runtest_makereport"),
    ("_pytest.runner", "pytest_runtest_call"),
    ("_pytest.python", "Function.runtest"),
    ("_pytest.python", "Function._getobj"),
    ("_pytest.python", "Function.function"),
    ("_pytest.python", "PyobjMixin.obj"),
    ("_pytest.python", "PyobjMixin._getobj"),
    ("_pytest.python", "pytest_pyfunc_call"),
    ("_pytest.unittest", "TestCaseFunction.runtest"),
    ("_pytest.main", "pytest_runtestloop"),
    ("_pytest.skipping", "pytest_runtest_makereport"),
)


def _resolve(module_name: str, dotted: str) -> Any:
    owner: Any = sys.modules.get(module_name)
    parts = dotted.split(".")
    for index, part in enumerate(parts):
        if owner is None:
            return None
        # Class attributes are compared as stored (the raw descriptor), so wrapping a
        # classmethod in a new classmethod is visible.
        if isinstance(owner, type) and index == len(parts) - 1:
            owner = owner.__dict__.get(part)
        else:
            owner = getattr(owner, part, None)
    return owner


_EMPTY_CELL = object()


def _function_print(function: Any) -> tuple[Any, ...]:
    """What a function runs: the object, its code, defaults, keyword defaults and the
    contents of its closure cells.  Compared element by element with ``is``, so an
    in-place ``__code__``/``__defaults__``/cell swap on the same object is a change."""
    function = getattr(function, "__func__", function)
    if not isinstance(function, types.FunctionType):
        return (function,)
    cells: list[Any] = []
    for cell in function.__closure__ or ():
        try:
            cells.append(cell.cell_contents)
        except ValueError:
            cells.append(_EMPTY_CELL)
    kwdefaults = function.__kwdefaults__ or {}
    return (
        function,
        function.__code__,
        tuple(function.__defaults__ or ()),
        tuple((key, kwdefaults[key]) for key in sorted(kwdefaults)),
        tuple(cells),
    )


def _fingerprint(obj: Any) -> tuple[Any, ...]:
    """Identity plus the content of every function behind ``obj`` (a function, bound
    method, classmethod/staticmethod or property); other objects by identity only."""
    if isinstance(obj, (classmethod, staticmethod)):
        functions = [obj.__func__]
    elif isinstance(obj, property):
        functions = [f for f in (obj.fget, obj.fset, obj.fdel) if f is not None]
    elif isinstance(obj, (types.FunctionType, types.MethodType)):
        functions = [obj]
    else:
        functions = []
    return (obj, tuple(_function_print(f) for f in functions))


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left is right


def _hookimpl_file(impl: Any) -> str:
    function = getattr(impl.function, "__func__", impl.function)
    code = getattr(function, "__code__", None)
    return str(Path(code.co_filename).resolve()) if code is not None else ""


# Packages whose whole loaded code is swept (#2815 review; pytest_asyncio because closure
# loads it explicitly and it wraps pytest_pyfunc_call): every function
# (raw from module and class ``__dict__``) by content, and every module-level and class
# attribute by identity.
# A tuple: ``str.startswith`` takes it directly (_module_changes).
SWEEP_PACKAGES = ("pytest", "_pytest", "pluggy", "pytest_asyncio")
# The hot subset re-checked around every test (the full sweep runs at session end).
PLUGGY_HOT = (
    ("pluggy._callers", "_multicall"),
    ("pluggy._hooks", "HookCaller.__call__"),
    ("pluggy._hooks", "HookCaller._hookexec"),
    ("pluggy._hooks", "HookCaller.call_historic"),
    ("pluggy._hooks", "HookImpl.__init__"),
    ("pluggy._manager", "PluginManager._hookexec"),
    ("pluggy._result", "Result.get_result"),
    ("pluggy._result", "Result.force_result"),
)
_MISSING = object()
# Attributes that pytest's own plugins legitimately (re)bind between the import-time
# baseline and the start of collection (pytest_configure / sessionstart).  Exact labels
# only; each was observed on an honest run (#2815 review round 3).  They are re-based at
# collection start, every other difference is PATCHED.  Each is pinned by identity to
# the value pytest itself writes (or left at its baseline value): a ``CONFIG_PINS`` key
# (#2811) or the label of the swept function pytest installs.
CONFIG_PIN_CONFIG = "@config"
CONFIG_PIN_PLUGINMANAGER = "@config.pluginmanager"
CONFIGURE_TIME_WRITES: dict[str, str] = {
    # _pytest.debugging.pytest_configure stores the config and plugin manager.
    "_pytest.debugging:pytestPDB._pluginmanager": CONFIG_PIN_PLUGINMANAGER,
    "_pytest.debugging:pytestPDB._config": CONFIG_PIN_CONFIG,
    # _pytest.legacypath.pytest_load_initial_conftests monkeypatches this in; accepted
    # only when the new value IS legacypath's own function as it was at the baseline.
    "_pytest.config:Config._getini_unknown_type": "_pytest.legacypath.Config__getini_unknown_type",
}


def _in_sweep(module_name: str) -> bool:
    return any(module_name == p or module_name.startswith(p + ".") for p in SWEEP_PACKAGES)


def _sweep_modules() -> dict[str, Any]:
    """name -> module object for every loaded sweep-package module."""
    return {n: m for n, m in list(sys.modules.items()) if m is not None and _in_sweep(n)}


def _package_dirs(modules: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """package name -> its ``__path__`` entries, copied at the baseline."""
    dirs: dict[str, tuple[str, ...]] = {}
    for name, module in modules.items():
        path = getattr(module, "__path__", None)
        if path is not None:
            dirs[name] = tuple(str(d) for d in path)
    return dirs


def _module_changes(
    baseline: dict[str, Any],
    audited: Any = (),
    package_dirs: dict[str, tuple[str, ...]] | None = None,
    exists: Any = os.path.exists,
) -> list[str]:
    """Sweep-package modules first imported after the baseline (#2811), or whose
    ``sys.modules`` entry is no longer the baseline module object (replaced, set to
    ``None`` or removed).

    ``audited`` holds the sweep-package names the ``import`` audit hook saw after the
    baseline: one that is gone from ``sys.modules`` by the time of a check (imported,
    used, then deleted) still counts as late when its file exists in the parent
    package's baseline directories (a probe for a module that does not exist does not).

    A late module was not swept, so nothing it defines is covered: its code could have
    been changed before any check saw it (a first-seen snapshot would bake that in), and
    an assertion-rewritten module cannot be compared with a plain compile of its file.
    So any late module fails closed.  An honest run imports none: with pytest 9.0,
    pluggy 1.6 and pytest-asyncio 1.3 every submodule is loaded at the baseline except
    ``_pytest.pytester_assertions`` (only for the ``pytester`` plugin),
    ``_pytest.terminalprogress`` (Windows or an explicit ``-p``, which loads it before
    the witness) and ``pytest.__main__``.
    """
    changes: list[str] = []
    current = dict(sys.modules)
    for name, module in current.items():
        if not name.startswith(SWEEP_PACKAGES) or not _in_sweep(name):
            continue
        known = baseline.get(name, _MISSING)
        if known is _MISSING:
            if module is not None:
                changes.append(f"late_module:{name}")
        elif known is not module:
            changes.append(f"module_replaced:{name}")
    for name in baseline:
        if name not in current:
            changes.append(f"module_removed:{name}")
    for name in list(audited):
        if name in baseline or name in current:
            continue
        parent, _, last = name.rpartition(".")
        dirs = (package_dirs or {}).get(parent, ())
        if any(
            exists(os.path.join(d, last + ".py")) or exists(os.path.join(d, last, "__init__.py"))
            for d in dirs
        ):
            changes.append(f"late_module:{name}")
    return changes


def _label(container: Any, attr: str) -> str:
    if isinstance(container, type):
        return f"{container.__module__}:{container.__qualname__}.{attr}"
    return f"{getattr(container, '__name__', '?')}.{attr}"


def _sweep() -> dict[str, tuple[Any, str, tuple[Any, ...]]]:
    """label -> (container, attribute, fingerprint) for every attribute of every loaded
    sweep module, and of every class those modules define (recursively for nested
    classes)."""
    entries: dict[str, tuple[Any, str, tuple[Any, ...]]] = {}
    seen: set[int] = set()

    def walk(container: Any, owner_module: str) -> None:
        if id(container) in seen:
            return
        seen.add(id(container))
        for attr, value in list(vars(container).items()):
            entries[_label(container, attr)] = (container, attr, _fingerprint(value))
            if isinstance(value, type) and getattr(value, "__module__", None) == owner_module:
                walk(value, owner_module)

    for name, module in list(sys.modules.items()):
        if module is not None and _in_sweep(name):
            walk(module, name)
    return entries


def _swept_changes(
    entries: dict[str, tuple[Any, str, tuple[Any, ...]]], allowed: frozenset[str] = frozenset()
) -> list[str]:
    changed: list[str] = []
    for label, (container, attr, original) in entries.items():
        if label in allowed:
            continue
        current = vars(container).get(attr, _MISSING)
        if current is _MISSING or not _same(_fingerprint(current), original):
            changed.append(label)
    return changed


def _hook_state(manager: Any) -> dict[str, tuple[Any, Any, list[Any]]]:
    """hook name -> (HookCaller, its ``_hookexec``, ordered hookimpls)."""
    state: dict[str, tuple[Any, Any, list[Any]]] = {}
    for name, caller in list(vars(manager.hook).items()):
        get = getattr(caller, "get_hookimpls", None)
        if callable(get):
            found: Any = get()
            state[name] = (caller, getattr(caller, "_hookexec", None), list(found))
    return state


def _plugin_file(plugin: Any) -> str:
    if isinstance(plugin, types.ModuleType):
        return str(getattr(plugin, "__file__", "") or "")
    cls = plugin if isinstance(plugin, type) else type(plugin)
    module = sys.modules.get(getattr(cls, "__module__", "") or "")
    return str(getattr(module, "__file__", "") or "") if module is not None else ""


def _test_code(item: Any) -> types.CodeType | None:
    obj = getattr(item, "obj", None)
    if obj is None:
        return None
    func = getattr(obj, "__func__", obj)
    try:
        func = inspect.unwrap(func)
    except ValueError:
        return None
    code = getattr(func, "__code__", None)
    return code if isinstance(code, types.CodeType) else None


def _skip_text(report: Any) -> str:
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        path, lineno, reason = longrepr
        return f"{path}:{lineno}: {reason}"
    return str(longrepr or "")[:2000]


def _make_emit(fd: int, key: bytes) -> Any:
    """Return the numbered, MAC'd JSON-lines writer for the inherited witness fd.

    The fd, the key and the library functions it uses are closure cells captured now,
    before any candidate code runs, not attributes a later monkeypatch could swap.
    """
    new, digest, dumps, write = hmac.new, hashlib.sha256, json.dumps, os.write
    seq = [0]

    def emit(record: dict[str, Any]) -> None:
        record = dict(record)
        record["seq"] = seq[0]
        seq[0] += 1
        body = dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        mac = new(key, body, digest).hexdigest().encode("ascii")
        view = memoryview(mac + b" " + body + b"\n")
        while view:
            view = view[write(fd, view) :]

    return emit


class _CodeWatch:
    """Observe one test's own code object through ``sys.monitoring``."""

    def __init__(self) -> None:
        self._mon = sys.monitoring
        events = self._mon.events
        self._local = events.PY_START | events.PY_RESUME | events.PY_RETURN | events.PY_YIELD
        self._global = events.PY_UNWIND | events.PY_THROW
        tool = next((tool for tool in (3, 4, 2, 0) if self._mon.get_tool(tool) is None), None)
        if tool is None:
            raise RuntimeError("no free sys.monitoring tool id for the verifier witness")
        self._tool: int = tool
        self._mon.use_tool_id(tool, WITNESS_TOOL_NAME)
        self._code: types.CodeType | None = None
        self._state: dict[str, Any] = {}
        register = self._mon.register_callback
        register(self._tool, events.PY_START, self._on_start)
        register(self._tool, events.PY_RESUME, self._on_resume)
        register(self._tool, events.PY_THROW, self._on_throw)
        register(self._tool, events.PY_RETURN, self._on_return)
        register(self._tool, events.PY_YIELD, self._on_yield)
        register(self._tool, events.PY_UNWIND, self._on_unwind)

    def _mine(self, code: types.CodeType) -> bool:
        return code is self._code

    def _on_start(self, code: types.CodeType, _offset: int) -> None:
        if self._mine(code):
            self._state["starts"] += 1
            self._state["depth"] += 1

    def _on_resume(self, code: types.CodeType, _offset: int) -> None:
        if self._mine(code):
            self._state["depth"] += 1

    def _on_throw(self, code: types.CodeType, _offset: int, _exc: BaseException) -> None:
        if self._mine(code):
            self._state["depth"] += 1

    def _on_return(self, code: types.CodeType, _offset: int, _value: object) -> None:
        if self._mine(code):
            self._state["depth"] -= 1
            if self._state["depth"] == 0:
                self._state["returns"] += 1

    def _on_yield(self, code: types.CodeType, _offset: int, _value: object) -> None:
        if self._mine(code):
            self._state["depth"] -= 1

    def _on_unwind(self, code: types.CodeType, _offset: int, exc: BaseException) -> None:
        if self._mine(code):
            self._state["depth"] -= 1
            self._state["unwinds"] += 1
            if len(self._state["unwind_types"]) < 5:
                cls = type(exc)
                self._state["unwind_types"].append(f"{cls.__module__}.{cls.__qualname__}")

    def begin(self, code: types.CodeType | None) -> None:
        self._code = code
        self._state = {"starts": 0, "returns": 0, "unwinds": 0, "depth": 0, "unwind_types": []}
        if code is not None:
            self._mon.set_local_events(self._tool, code, self._local)
            self._mon.set_events(self._tool, self._global)

    def end(self) -> dict[str, Any]:
        code, self._code = self._code, None
        if code is not None:
            self._mon.set_events(self._tool, 0)
            self._mon.set_local_events(self._tool, code, 0)
        return dict(self._state)


def _code_identity(code: types.CodeType | None) -> dict[str, Any]:
    if code is None:
        return {"code_file": "", "code_qualname": "", "code_firstlineno": 0}
    return {
        "code_file": str(Path(code.co_filename).resolve()),
        "code_qualname": str(getattr(code, "co_qualname", code.co_name)),
        "code_firstlineno": int(code.co_firstlineno),
    }


class _PluginHolder:
    """Hashable holder for the hook functions (pluggy and pytest index plugins)."""


def _build_plugin(emit: Any) -> tuple[Any, Any]:
    """The pytest plugin: plain functions closing over ``emit`` and the watch.

    pluggy keeps references to these function objects when the plugin is registered, so
    replacing attributes of the returned namespace afterwards changes nothing.
    """
    watch = _CodeWatch()
    # Import-time baseline (#2815 r3): taken while pytest imports this module for ``-p``,
    # before any conftest, tree plugin or test module, so before any candidate code.
    internals: list[tuple[str, str, Any]] = [
        (m, d, _fingerprint(_resolve(m, d))) for m, d in (*PYTEST_INTERNALS, *PLUGGY_HOT)
    ]
    sweep: dict[str, tuple[Any, str, tuple[Any, ...]]] = _sweep()
    modules: dict[str, Any] = _sweep_modules()
    package_dirs = _package_dirs(modules)
    exists = os.path.exists
    audited: dict[str, None] = {}

    def audit(event: str, args: Any) -> None:
        # Audit hooks cannot be removed; this one only records names (#2811 review).
        if event == "import" and args and isinstance(args[0], str):
            name = args[0]
            if name.startswith(SWEEP_PACKAGES) and name not in modules and _in_sweep(name):
                audited[name] = None

    sys.addaudithook(audit)
    configs: list[Any] = []
    # hook name -> (caller, its _hookexec, ordered impls, {id: (impl, function, print)})
    hooks: dict[str, tuple[Any, Any, list[Any], dict[int, tuple[Any, Any, Any]]]] = {}
    managers: list[tuple[Any, Any]] = []
    patched: dict[str, None] = {}
    added: dict[tuple[str, str], None] = {}

    def check_hooks() -> None:
        if not managers:
            return
        manager, inner = managers[0]
        if getattr(manager, "_inner_hookexec", None) is not inner:
            patched["pluggy:PluginManager._inner_hookexec"] = None
        current = _hook_state(manager)
        for name, (caller, hookexec, impls, known) in hooks.items():
            now = current.get(name)
            if now is None or now[0] is not caller:
                patched[f"hookcaller_replaced:{name}"] = None
                continue
            if now[1] is not hookexec:
                patched[f"hookcaller_hookexec:{name}"] = None
            ids = {id(impl) for impl in now[2]}
            for impl in impls:
                if id(impl) not in ids:
                    patched[f"hookimpl_removed:{name}:{impl.plugin_name}"] = None
            if [i for i in now[2] if id(i) in known] != [i for i in impls if id(i) in ids]:
                patched[f"hookimpl_reordered:{name}"] = None
            for impl in now[2]:
                entry = known.get(id(impl))
                if entry is None or entry[0] is not impl:
                    added[(str(getattr(impl, "plugin_name", "")), _hookimpl_file(impl))] = None
                elif entry[1] is not impl.function or not _same(
                    _function_print(impl.function), entry[2]
                ):
                    patched[f"hookimpl:{name}:{impl.plugin_name}"] = None
        for name, (_caller, _hookexec, impls) in current.items():
            if name not in hooks:
                for impl in impls:
                    added[(str(getattr(impl, "plugin_name", "")), _hookimpl_file(impl))] = None

    def check_hot() -> None:
        for m, d, original in internals:
            if not _same(_fingerprint(_resolve(m, d)), original):
                patched[f"{m}:{d}"] = None
        check_hooks()
        for change in _module_changes(modules, audited, package_dirs, exists):
            patched[change] = None

    def check_all(allowed: frozenset[str] = frozenset()) -> None:
        if not managers:
            # The hook baseline is taken when pytest registers this module; without it
            # nothing was compared, so the run proves nothing (fail closed).
            patched["witness:snapshot_not_taken"] = None
        check_hot()
        for change in _swept_changes(sweep, allowed):
            patched[change] = None

    def baseline_hooks(manager: Any) -> None:
        """Hook-state baseline, taken when pytest registers this module for ``-p``."""
        if managers:
            return
        managers[:] = [(manager, getattr(manager, "_inner_hookexec", None))]
        for name, (caller, hookexec, impls) in _hook_state(manager).items():
            hooks[name] = (
                caller,
                hookexec,
                impls,
                {id(i): (i, i.function, _function_print(i.function)) for i in impls},
            )

    def rebase_allowed(session: Any) -> None:
        # Pins (#2811): the config this witness was configured with (it must also be the
        # session's) and the plugin manager it registered with at ``-p`` time.
        config = configs[0] if configs else _MISSING
        if getattr(session, "config", _MISSING) is not config:
            config = _MISSING
        pins = {
            CONFIG_PIN_CONFIG: config,
            CONFIG_PIN_PLUGINMANAGER: managers[0][0] if managers else _MISSING,
        }
        for label, source in CONFIGURE_TIME_WRITES.items():
            entry = sweep.get(label)
            if entry is None:
                continue
            container, attr, old = entry
            value = vars(container).get(attr, _MISSING)
            if source in pins:
                expected_value = pins[source]
            else:
                expected = sweep.get(source)
                expected_value = expected[2][0] if expected is not None else _MISSING
            if value is _MISSING or (value is not old[0] and value is not expected_value):
                patched[label] = None
                continue
            sweep[label] = (container, attr, _fingerprint(value))

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection(session: Any) -> Any:
        # Second snapshot when collection starts: everything that ran since the
        # import-time baseline (initial conftests, plugin configure) is diffed against
        # it.  Only the exact CONFIGURE_TIME_WRITES are re-based; any other difference
        # is PATCHED (sticky).
        check_all(allowed=frozenset(CONFIGURE_TIME_WRITES))
        rebase_allowed(session)
        yield

    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(config: pytest.Config) -> None:
        if not configs:
            configs.append(config)
        emit({
            "t": "begin",
            "pytest": pytest.__version__,
            "python": sys.version.split()[0],
            "rootpath": str(config.rootpath),
        })

    def pytest_plugin_registered(plugin: Any, manager: Any) -> None:
        try:
            name = manager.get_name(plugin)
        except Exception:  # noqa: BLE001 - a hostile plugin must not stop the record
            name = None
        emit({"t": "plugin", "name": str(name), "file": _plugin_file(plugin)})

    def pytest_itemcollected(item: Any) -> None:
        emit({"t": "item", "nodeid": item.nodeid})

    def pytest_collectreport(report: Any) -> None:
        if report.skipped:
            emit({"t": "collect_skip", "nodeid": report.nodeid, "text": _skip_text(report)})
        elif report.failed:
            emit({"t": "collect_error", "nodeid": report.nodeid})

    def pytest_collection_finish(session: Any) -> None:
        emit({"t": "selected", "nodeids": [i.nodeid for i in session.items]})

    def pytest_deselected(items: Any) -> None:
        emit({"t": "deselected", "nodeids": [i.nodeid for i in items]})

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_protocol(item: Any, nextitem: Any) -> Any:
        code = _test_code(item)
        check_hot()
        watch.begin(code)
        try:
            yield
        finally:
            state = watch.end()
            check_hot()
            emit({"t": "witness", "nodeid": item.nodeid, **state, **_code_identity(code)})

    def pytest_runtest_logreport(report: Any) -> None:
        emit({
            "t": "report",
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "wasxfail": hasattr(report, "wasxfail"),
            "text": _skip_text(report) if report.skipped else "",
        })

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
        check_all()
        emit({
            "t": "end",
            "exitstatus": int(exitstatus),
            "patched": list(patched),
            "hookimpls_added": [{"plugin": p, "file": f} for p, f in added],
        })

    plugin = _PluginHolder()
    for name, function in dict(
        pytest_configure=pytest_configure,
        pytest_collection=pytest_collection,
        pytest_plugin_registered=pytest_plugin_registered,
        pytest_itemcollected=pytest_itemcollected,
        pytest_collectreport=pytest_collectreport,
        pytest_collection_finish=pytest_collection_finish,
        pytest_deselected=pytest_deselected,
        pytest_runtest_protocol=pytest_runtest_protocol,
        pytest_runtest_logreport=pytest_runtest_logreport,
        pytest_sessionfinish=pytest_sessionfinish,
    ).items():
        setattr(plugin, name, function)
    return plugin, baseline_hooks


def _open_channel() -> Any:
    try:
        fd = int(os.environ.pop(WITNESS_FD_ENV))
        key_fd = int(os.environ.pop(WITNESS_KEY_FD_ENV))
    except (KeyError, ValueError) as exc:
        raise RuntimeError("verifier witness started without its channel") from exc
    # The plugin directory reached sys.path through PYTHONPATH; candidate subprocesses
    # do not need it.
    os.environ.pop("PYTHONPATH", None)
    key = b""
    while len(key) < WITNESS_KEY_BYTES:
        chunk = os.read(key_fd, WITNESS_KEY_BYTES - len(key))
        if not chunk:
            break
        key += chunk
    os.close(key_fd)
    if len(key) != WITNESS_KEY_BYTES:
        raise RuntimeError("verifier witness key incomplete")
    os.set_inheritable(fd, False)
    return _make_emit(fd, key)


# Opened at import, i.e. while pytest pre-parses ``-p``: before any test module, and so
# before any candidate code, is imported.  Importing this module elsewhere (no channel in
# the environment) leaves it inert.
_WITNESS, _BASELINE_HOOKS = (
    _build_plugin(_open_channel()) if WITNESS_FD_ENV in os.environ else (None, None)
)


def pytest_plugin_registered(plugin: Any, manager: Any) -> None:
    # Historic hook: the first call happens while pytest registers this module for
    # ``-p`` (Config._preparse -> consider_preparse), before pytest_load_initial_conftests
    # imports any conftest.  The hook-state baseline is taken then.
    if _BASELINE_HOOKS is not None:
        _BASELINE_HOOKS(manager)


def pytest_configure(config: pytest.Config) -> None:
    global _WITNESS, _BASELINE_HOOKS
    plugin, _WITNESS, _BASELINE_HOOKS = _WITNESS, None, None
    if plugin is None:
        raise pytest.UsageError("verifier witness loaded without its channel")
    config.pluginmanager.register(plugin, "nexus-eia-verifier-witness")
    # Nothing importable by name points at the witness any more (#2808 review).  A
    # candidate that targets the witness can still reach it through the plugin manager
    # or closure cells: that is the documented residual, not a P1 route.
    sys.modules.pop(__name__, None)
