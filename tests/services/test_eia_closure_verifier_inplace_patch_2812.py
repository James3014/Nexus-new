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
    assert any(
        entry.startswith("hookimpl:") for entry in row["witness"]["pytest_internals_patched"]
    ), row["witness"]
