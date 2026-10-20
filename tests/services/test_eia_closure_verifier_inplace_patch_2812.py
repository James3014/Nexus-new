"""EIA closure verifier: in-place mutation of pytest's call path is detected (#2812).

The #2795 confirmer (workspace-06) showed that swapping ``__code__`` on
``_pytest.python.pytest_pyfunc_call`` at import kept the function object, so the
identity snapshot in #2808 missed it and a failing verifier was reported PASSED.  The
witness now snapshots the content of every snapshotted internal (code, defaults,
keyword defaults, closure cell contents) and of every hookimpl registered when it
configures, re-checks them around every test and at session end, and reports
hookimpls that appear later so the parent can judge their file.

Each candidate below makes a failing test look passed to pytest; the verifier must
report ``VERIFIER_PYTEST_INTERNALS_PATCHED``.  Runs on Linux (unsandboxed) and macOS
(sandbox-exec).
"""

from __future__ import annotations

import pytest

from nexus.services.external_intelligence_closure import (
    VERIFIER_PYTEST_INTERNALS_PATCHED,
)
from tests.services.test_external_intelligence_closure_out_of_process_2795 import (
    _repo,
    _row,
    _spec,
)

# The confirmer's route (issuecomment-6287425794): the swapped-in code sets the test
# module's VALUE global to the expected value, then really calls the test function, so
# the test's own code object starts and returns without an unwind.
_SWAP_PYFUNC_CALL_CODE = (
    "import _pytest.python as _pp\n"
    "def _fake(pyfuncitem):\n"
    "    pyfuncitem.obj.__globals__['VALUE'] = 2\n"
    "    pyfuncitem.obj()\n"
    "    return True\n"
    "_pp.pytest_pyfunc_call.__code__ = _fake.__code__\n"
    "VALUE = 3\n"
)
# Same object, new code: the test is never called.
_SWAP_RUNTEST_CODE = (
    "import _pytest.python as _pp\n"
    "def _noop(self):\n"
    "    return None\n"
    "_pp.Function.runtest.__code__ = _noop.__code__\n"
    "VALUE = 3\n"
)
# Same object and code, new defaults: reports are no longer logged.
_MUTATE_DEFAULTS = (
    "import _pytest.runner as _r\n_r.call_and_report.__defaults__ = (False,)\nVALUE = 3\n"
)
# A new hookwrapper injected into the existing makereport caller under a trusted
# plugin's name, without registering any plugin.
_INJECT_HOOKIMPL = (
    "import gc\n"
    "import _pytest.runner as _r\n"
    "from _pytest.config import PytestPluginManager\n"
    "from pluggy import HookimplOpts\n"
    "from pluggy._hooks import HookImpl\n"
    "def _wrapper(item, call):\n"
    "    outcome = yield\n"
    "    report = outcome.get_result()\n"
    "    report.outcome = 'passed'\n"
    "    report.longrepr = None\n"
    "_pm = next(o for o in gc.get_objects() if isinstance(o, PytestPluginManager))\n"
    "_opts = HookimplOpts(wrapper=False, hookwrapper=True, optionalhook=False,\n"
    "                     tryfirst=True, trylast=False, specname=None)\n"
    "_pm.hook.pytest_runtest_makereport._add_hookimpl(\n"
    "    HookImpl(_r, '_pytest.runner', _wrapper, _opts))\n"
    "VALUE = 3\n"
)


@pytest.mark.parametrize(
    ("source", "marker"),
    [
        (_SWAP_PYFUNC_CALL_CODE, "_pytest.python:pytest_pyfunc_call"),
        (_SWAP_RUNTEST_CODE, "_pytest.python:Function.runtest"),
        (_MUTATE_DEFAULTS, "_pytest.runner:call_and_report"),
        (_INJECT_HOOKIMPL, "hookimpl_added:_pytest.runner:"),
    ],
    ids=["pyfunc_call_code_swap", "runtest_code_swap", "defaults_mutation", "hookimpl_injection"],
)
def test_in_place_mutation_of_pytest_call_path_is_not_passed(tmp_path, source, marker):
    root, base, cand = _repo(tmp_path, {"src_mod.py": source})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert any(entry.startswith(marker) for entry in row["witness"]["pytest_internals_patched"]), (
        row["witness"]
    )


def test_confirmer_route_fools_pytest_itself(tmp_path):
    """Control: the route really turns the failing test green for pytest (rc=0), so the
    refusal above comes from the witness, not from a test that failed anyway."""
    root, base, cand = _repo(tmp_path, {"src_mod.py": _SWAP_PYFUNC_CALL_CODE})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["witness"]["forged_node_ids"] == []
    assert row["passed"] is False


def test_honest_candidate_still_passes_with_the_content_snapshot(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["pytest_internals_patched"] == []


# Swaps the code at import and puts the original back as soon as it has been used, so
# nothing is left to see at session end: only the check around each test catches it.
_SWAP_AND_RESTORE = (
    "import _pytest.python as _pp\n"
    "_original = _pp.pytest_pyfunc_call.__code__\n"
    "def _fake(pyfuncitem):\n"
    "    import _pytest.python as _pp2\n"
    "    pyfuncitem.obj.__globals__['VALUE'] = 2\n"
    "    pyfuncitem.obj()\n"
    "    _pp2.pytest_pyfunc_call.__code__ = _pp2._nexus_saved_code_2812\n"
    "    return True\n"
    "_pp._nexus_saved_code_2812 = _original\n"
    "_pp.pytest_pyfunc_call.__code__ = _fake.__code__\n"
    "VALUE = 3\n"
)


def test_swap_restored_after_use_is_caught_by_the_per_test_check(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": _SWAP_AND_RESTORE})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row


# A hookimpl that is not in the PYTEST_INTERNALS list: the session's failure counter.
# Swapping its code makes pytest exit 0 although the test failed; only the hookimpl
# content snapshot taken at configure sees the change.
_SWAP_SESSION_COUNTER_CODE = (
    "import _pytest.main as _m\n"
    "def _ignore(self, report):\n"
    "    return None\n"
    "_m.Session.pytest_runtest_logreport.__code__ = _ignore.__code__\n"
    "VALUE = 3\n"
)


def test_code_swap_on_a_registered_hookimpl_outside_the_internals_list_is_caught(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": _SWAP_SESSION_COUNTER_CODE})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    # Session's hookimpl registers after the baseline; since #2815 the module sweep
    # sees the swapped method itself.
    assert any(
        "pytest_runtest_logreport" in entry for entry in row["witness"]["pytest_internals_patched"]
    ), row["witness"]


# --- #2815 review round 2: whole-module sweep, removed and reordered hookimpls ------

_FIND_PM = (
    "import gc\n"
    "from _pytest.config import PytestPluginManager\n"
    "_pm = next(o for o in gc.get_objects() if isinstance(o, PytestPluginManager))\n"
)
_ROUTES_2815 = {
    # In-place closure-cell change on a swept function (same behaviour, other object).
    "closure_cell": (
        "import functools\n"
        "import _pytest.subtests as _st\n"
        "_cell = _st.capturing_output.__closure__[0]\n"
        "_inner = _cell.cell_contents\n"
        "_cell.cell_contents = functools.wraps(_inner)(lambda *a, **k: _inner(*a, **k))\n"
        "VALUE = 3\n",
        "_pytest.subtests",
    ),
    # In-place code swap on pluggy's call loop (an equal copy: behaviour unchanged).
    "multicall_code_swap": (
        "import pluggy._callers as _c\n"
        "_c._multicall.__code__ = _c._multicall.__code__.replace()\n"
        "VALUE = 3\n",
        "pluggy._callers:_multicall",
    ),
    # A rebound module global in _pytest.runner (not in the hot list).
    "runner_global_rebound": (
        "import _pytest.runner as _r\n"
        "_orig = _r.show_test_item\n"
        "_r.show_test_item = lambda item: _orig(item)\n"
        "VALUE = 3\n",
        "show_test_item",
    ),
    # A whole plugin's hookimpls removed after the snapshot.
    "hookimpl_removed": (
        _FIND_PM + "_pm.unregister(_pm.get_plugin('skipping'))\nVALUE = 3\n",
        "hookimpl_removed:",
    ),
    # The order of an existing caller's hookimpls changed.
    "hookimpl_reordered": (
        _FIND_PM + "_pm.hook.pytest_runtest_setup._hookimpls.reverse()\nVALUE = 3\n",
        "hookimpl_reordered:pytest_runtest_setup",
    ),
}


@pytest.mark.parametrize("route", sorted(_ROUTES_2815))
def test_swept_and_hook_state_changes_are_patched(tmp_path, route):
    source, marker = _ROUTES_2815[route]
    root, base, cand = _repo(tmp_path, {"src_mod.py": source})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert any(marker in entry for entry in row["witness"]["pytest_internals_patched"]), row[
        "witness"
    ]


# Swapped at import, put back by candidate code the test itself calls: the end-of-session
# sweep sees the original again, so only the hot check before the test catches it.
_MULTICALL_RESTORED = (
    "import pluggy._callers as _c\n"
    "_saved = _c._multicall.__code__\n"
    "_c._multicall.__code__ = _saved.replace()\n"
    "def check():\n"
    "    _c._multicall.__code__ = _saved\n"
)


def test_pluggy_hot_path_swap_restored_by_the_test_is_caught_around_the_test(tmp_path):
    keep = "from src_mod import check\n\n\ndef test_keep():\n    check()\n"
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": _MULTICALL_RESTORED},
        base={"src_mod.py": "def check():\n    return None\n", "tests/test_keep.py": keep},
    )
    row = _row(root, base, cand, _spec("tests/test_keep.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert "pluggy._callers:_multicall" in row["witness"]["pytest_internals_patched"]


def test_classmethod_entries_are_compared_raw_and_never_flag_an_honest_run(tmp_path):
    from _pytest.reports import TestReport

    from nexus.services.external_intelligence_verifier_witness import (
        _fingerprint,
        _resolve,
        _same,
    )

    raw = _fingerprint(_resolve("_pytest.reports", "TestReport.from_item_and_call"))
    assert _same(raw, _fingerprint(_resolve("_pytest.reports", "TestReport.from_item_and_call")))
    # Through getattr each access binds a new method object, which is why the witness
    # reads class ``__dict__`` entries raw and never compares bound methods.
    assert not _same(
        _fingerprint(TestReport.from_item_and_call), _fingerprint(TestReport.from_item_and_call)
    )
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert not any("from_item_and_call" in e for e in row["witness"]["pytest_internals_patched"])


def test_base_unchanged_subdirectory_conftest_with_hooks_is_trusted(tmp_path):
    conftest = (
        "import pytest\n\n\n"
        "def pytest_runtest_setup(item):\n    item.user_properties.append(('seen', 1))\n\n\n"
        "@pytest.fixture\ndef sub_value():\n    return 2\n"
    )
    sub_test = "def test_sub(sub_value):\n    assert sub_value == 2\n"
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n"},
        base={"tests/sub/conftest.py": conftest, "tests/sub/test_sub.py": sub_test},
    )
    row = _row(root, base, cand, _spec("tests/sub/test_sub.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["pytest_internals_patched"] == []
    assert row["witness"]["foreign_plugins"] == []


# pytest-asyncio's own pytest_pyfunc_call wrapper is on the call path of async tests.
_SWAP_ASYNCIO_PYFUNC_CALL = (
    "import pytest_asyncio.plugin as _pa\n"
    "_pa.pytest_pyfunc_call.__code__ = _pa.pytest_pyfunc_call.__code__.replace()\n"
    "VALUE = 3\n"
)


def test_code_swap_on_the_pytest_asyncio_call_wrapper_is_patched(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": _SWAP_ASYNCIO_PYFUNC_CALL},
        base={"pytest.ini": "[pytest]\nasyncio_mode = auto\n"},
    )
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert any(
        "pytest_asyncio" in e or "pytest_pyfunc_call" in e
        for e in row["witness"]["pytest_internals_patched"]
    ), row["witness"]


# --- #2815 review round 3: candidate code that runs before collection ---------------

_PRELOAD_TEST = "from mypkg import VALUE\n\n\ndef test_value():\n    assert VALUE == 2\n"


def _preload_case(tmp_path, candidate_files, base_conftest, authorized):
    base = {"mypkg/__init__.py": "VALUE = 1\n", "tests/test_mod.py": _PRELOAD_TEST}
    if base_conftest is not None:
        base["conftest.py"] = base_conftest
    root, b, c = _repo(tmp_path, candidate_files, base=base)
    return _row(root, b, c, _spec("tests/test_mod.py"), authorized)


def test_swap_by_a_package_a_base_conftest_preloads_is_patched(tmp_path):
    """The #2815 reviewer's repro: a base-unchanged root conftest imports ``mypkg`` while
    pytest loads initial conftests; the candidate's ``mypkg/__init__.py`` swaps
    ``pytest_pyfunc_call.__code__`` then.  The import-time baseline predates it."""
    row = _preload_case(
        tmp_path,
        {"mypkg/__init__.py": _SWAP_PYFUNC_CALL_CODE},
        "import mypkg  # noqa: F401\n",
        ["mypkg/__init__.py"],
    )
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert "_pytest.python:pytest_pyfunc_call" in row["witness"]["pytest_internals_patched"]


def test_swap_in_a_submodule_a_base_conftest_preloads_is_patched(tmp_path):
    row = _preload_case(
        tmp_path,
        {
            "mypkg/__init__.py": "from mypkg import _impl  # noqa: F401\nVALUE = 3\n",
            "mypkg/_impl.py": _SWAP_PYFUNC_CALL_CODE,
        },
        "import mypkg  # noqa: F401\n",
        ["mypkg"],
    )
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row


def test_swap_in_an_authorized_changed_conftest_is_patched(tmp_path):
    row = _preload_case(
        tmp_path,
        {"conftest.py": _SWAP_PYFUNC_CALL_CODE, "mypkg/__init__.py": "VALUE = 3\n"},
        "",
        ["conftest.py", "mypkg/__init__.py"],
    )
    assert row["root_shadowing_authorized_paths"] == ["conftest.py"]
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row


def test_honest_suite_with_the_debugging_plugin_active_is_not_flagged(tmp_path):
    """pytest's debugging (and legacypath) plugins write class attributes during
    configure; only those exact, allow-listed writes are re-based."""
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n"},
        base={"pytest.ini": "[pytest]\nasyncio_mode = auto\n", "conftest.py": "import os\n"},
    )
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["pytest_internals_patched"] == []


def test_allow_listed_attribute_rebound_by_preloaded_candidate_code_is_patched(tmp_path):
    """The allowlist is pinned to the value pytest itself writes: candidate code that
    rebinds ``Config._getini_unknown_type`` to its own function is still PATCHED."""
    swap = (
        "from _pytest.config import Config\n"
        "Config._getini_unknown_type = lambda self, name, type, value: value\n"
        "VALUE = 3\n"
    )
    row = _preload_case(
        tmp_path, {"mypkg/__init__.py": swap}, "import mypkg  # noqa: F401\n", ["mypkg"]
    )
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert (
        "_pytest.config:Config._getini_unknown_type" in row["witness"]["pytest_internals_patched"]
    )
