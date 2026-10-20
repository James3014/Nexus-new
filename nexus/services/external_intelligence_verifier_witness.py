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

The emitter, key and fd are closure cells captured at import, and the module removes
itself from ``sys.modules`` once its plugin is registered, so ``import``-by-name and
attribute patches no longer reach them (#2808 review).

Residual (documented in the PR): this is not a security boundary against a candidate that
knows about the witness.  The plugin and its closure cells stay reachable through the
plugin manager and ``gc``, and closure cells are writable, so a short targeted
monkeypatch can still rewrite the records.  Witness-targeted routes are out of scope for
P1 of #2795; the candidate diff review and the claim ceiling are the backstop.
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
# pytest internals a candidate would patch to rewrite outcomes.  Their identity is taken
# at ``pytest_configure`` (before collection imports candidate code) and compared again
# at session end.
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


def _build_plugin(emit: Any) -> Any:
    """The pytest plugin: plain functions closing over ``emit`` and the watch.

    pluggy keeps references to these function objects when the plugin is registered, so
    replacing attributes of the returned namespace afterwards changes nothing.
    """
    watch = _CodeWatch()
    internals: list[tuple[str, str, Any]] = []

    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(config: pytest.Config) -> None:
        internals[:] = [(m, d, _resolve(m, d)) for m, d in PYTEST_INTERNALS]
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
        watch.begin(code)
        try:
            yield
        finally:
            state = watch.end()
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
        patched = [f"{m}:{d}" for m, d, original in internals if _resolve(m, d) is not original]
        emit({"t": "end", "exitstatus": int(exitstatus), "patched": patched})

    plugin = _PluginHolder()
    for name, function in dict(
        pytest_configure=pytest_configure,
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
    return plugin


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
_WITNESS = _build_plugin(_open_channel()) if WITNESS_FD_ENV in os.environ else None


def pytest_configure(config: pytest.Config) -> None:
    global _WITNESS
    plugin, _WITNESS = _WITNESS, None
    if plugin is None:
        raise pytest.UsageError("verifier witness loaded without its channel")
    config.pluginmanager.register(plugin, "nexus-eia-verifier-witness")
    # Nothing importable by name points at the witness any more (#2808 review).  A
    # candidate that targets the witness can still reach it through the plugin manager
    # or closure cells: that is the documented residual, not a P1 route.
    sys.modules.pop(__name__, None)
