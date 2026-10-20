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

Residual (documented in the PR): code that targets this witness specifically, e.g. by
extracting the key from interpreter memory, is not stopped here; the candidate diff
review and independent acceptance remain the backstop.
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


class _Channel:
    """Numbered, MAC'd JSON lines on the inherited witness fd."""

    def __init__(self, fd: int, key: bytes) -> None:
        # Bound now: later patches of these module attributes do not reach the channel.
        self._fd = fd
        self._key = key
        self._seq = 0
        self._new = hmac.new
        self._digest = hashlib.sha256
        self._dumps = json.dumps
        self._write = os.write

    def emit(self, record: dict[str, Any]) -> None:
        record = dict(record)
        record["seq"] = self._seq
        self._seq += 1
        payload = self._dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        body = payload.encode("utf-8")
        mac = self._new(self._key, body, self._digest).hexdigest().encode("ascii")
        view = memoryview(mac + b" " + body + b"\n")
        while view:
            written = self._write(self._fd, view)
            view = view[written:]


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


class VerifierWitness:
    """The pytest plugin object (registered by ``pytest_configure`` below)."""

    def __init__(self, channel: _Channel) -> None:
        self._channel = channel
        self._watch = _CodeWatch()
        self._internals: list[tuple[str, str, Any]] = []

    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(self, config: pytest.Config) -> None:
        self._internals = [(m, d, _resolve(m, d)) for m, d in PYTEST_INTERNALS]
        self._channel.emit({
            "t": "begin",
            "pytest": pytest.__version__,
            "python": sys.version.split()[0],
            "rootpath": str(config.rootpath),
        })

    def pytest_plugin_registered(self, plugin: Any, manager: Any) -> None:
        try:
            name = manager.get_name(plugin)
        except Exception:  # noqa: BLE001 - a hostile plugin must not stop the record
            name = None
        self._channel.emit({"t": "plugin", "name": str(name), "file": _plugin_file(plugin)})

    def pytest_itemcollected(self, item: Any) -> None:
        self._channel.emit({"t": "item", "nodeid": item.nodeid})

    def pytest_collectreport(self, report: Any) -> None:
        if report.skipped:
            self._channel.emit({
                "t": "collect_skip",
                "nodeid": report.nodeid,
                "text": _skip_text(report),
            })
        elif report.failed:
            self._channel.emit({"t": "collect_error", "nodeid": report.nodeid})

    def pytest_collection_finish(self, session: Any) -> None:
        self._channel.emit({"t": "selected", "nodeids": [i.nodeid for i in session.items]})

    def pytest_deselected(self, items: Any) -> None:
        self._channel.emit({"t": "deselected", "nodeids": [i.nodeid for i in items]})

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_protocol(self, item: Any, nextitem: Any) -> Any:
        code = _test_code(item)
        self._watch.begin(code)
        try:
            yield
        finally:
            state = self._watch.end()
            state["code_file"] = str(Path(code.co_filename).resolve()) if code else ""
            self._channel.emit({"t": "witness", "nodeid": item.nodeid, **state})

    def pytest_runtest_logreport(self, report: Any) -> None:
        self._channel.emit({
            "t": "report",
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "wasxfail": hasattr(report, "wasxfail"),
            "text": _skip_text(report) if report.skipped else "",
        })

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: Any, exitstatus: Any) -> None:
        patched = [
            f"{m}:{d}" for m, d, original in self._internals if _resolve(m, d) is not original
        ]
        self._channel.emit({"t": "end", "exitstatus": int(exitstatus), "patched": patched})


def _open_channel() -> _Channel:
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
    return _Channel(fd, key)


# Opened at import, i.e. while pytest pre-parses ``-p``: before any test module, and so
# before any candidate code, is imported.  Importing this module elsewhere (no channel in
# the environment) leaves it inert.
_WITNESS = VerifierWitness(_open_channel()) if WITNESS_FD_ENV in os.environ else None


def pytest_configure(config: pytest.Config) -> None:
    if _WITNESS is None:
        raise pytest.UsageError("verifier witness loaded without its channel")
    config.pluginmanager.register(_WITNESS, "nexus-eia-verifier-witness")
