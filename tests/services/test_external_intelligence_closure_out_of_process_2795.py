"""EIA closure verifier: out-of-process evidence and base-run skip comparison (#2795).

Candidate code runs inside the pytest process.  Each test below builds a small git
repository whose base passes or fails a test, applies one fake-pass route in the
candidate commit, and runs the closure's verifier runner on the candidate checkout.

P1 routes (each must be reported as not passed):
  * forging the JUnit report (writing a report file, or writing records into the
    inherited witness pipe);
  * patching pytest's reporting at import (``_pytest.reports`` / ``Function.runtest``,
    and an internal the witness does not snapshot, to show the code-object witness
    alone still refuses);
  * loading itself as a plugin through a test module's ``pytest_plugins``.

P2 (skips): a skip passes only if the same node is also skipped when the same verifier
runs at the base commit.  ``unittest.SkipTest``, ``pytest.skip.Exception(...,
_use_item_location=True)`` and ``functools.partial(pytest.skip)`` raised by candidate
code on a node that passes at base are not passed.

All of this runs on Linux (no sandbox: the row says so) and on macOS (under
``sandbox-exec``); the real-Seatbelt witnesses are in
``test_eia_closure_verifier_seatbelt_witness_2795.py``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.engine.sandboxed_lane import os_sandbox_available
from nexus.services import external_intelligence_verifier_witness as witness_plugin
from nexus.services.external_intelligence_closure import (
    _XML_INVALID_CHARS,
    UNIT_VERIFICATION_SCHEMA,
    VERIFIER_ENV_ALLOWLIST,
    VERIFIER_EVIDENCE_TAMPERED,
    VERIFIER_FOREIGN_PLUGIN,
    VERIFIER_JUNIT_FAILURES,
    VERIFIER_JUNIT_MISSING,
    VERIFIER_JUNIT_SKIPPED,
    VERIFIER_OUTCOME_FORGED,
    VERIFIER_PYTEST_INTERNALS_PATCHED,
    VERIFIER_TESTS_DESELECTED,
    VERIFIER_WITNESS_ENV_KEYS,
    VERIFIER_WITNESS_FD_ENV,
    VERIFIER_WITNESS_KEY_FD_ENV,
    VERIFIER_WITNESS_TAMPERED,
    _parse_witness,
    _run_verifier_specs,
    _witness_outcomes,
)

_BASE_SRC = "VALUE = 1\n\n\ndef check():\n    return None\n"
# Fails at base and at the candidate unless the candidate really sets VALUE = 2.
_TEST_NEEDS_TWO = "from src_mod import VALUE\n\n\ndef test_value():\n    assert VALUE == 2\n"
# Passes at base; a candidate can only make it skip.
_TEST_KEEP = "from src_mod import check\n\n\ndef test_keep():\n    check()\n"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _repo(
    tmp_path: Path, candidate: dict[str, str], base: dict[str, str] | None = None
) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "nexus-test@example.invalid")
    _git(root, "config", "user.name", "Nexus Test")
    _git(root, "config", "commit.gpgsign", "false")
    files = {"src_mod.py": _BASE_SRC, "tests/test_mod.py": _TEST_NEEDS_TWO}
    _write(root, {**files, **(base or {})})
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD")
    _write(root, candidate)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "candidate")
    return root, base_sha, _git(root, "rev-parse", "HEAD")


def _spec(*args: str) -> dict:
    return {"id": "pytest", "argv": [sys.executable, "-m", "pytest", "-q", *args]}


def _row(root: Path, base: str, cand: str, spec: dict, authorized: list[str]) -> dict:
    verification = _run_verifier_specs(
        task_id="t-2795",
        unit_id="u-2795",
        workspace_path=str(root),
        candidate_commit=cand,
        specs=[spec],
        schema=UNIT_VERIFICATION_SCHEMA,
        scope="UNIT",
        base_sha=base,
        authorized_paths=authorized,
        deletable_paths=(),
    )
    (row,) = verification["results"]
    assert (verification["status"] == "PASS") is row["passed"]
    return row


# --- P1 route 1: forging the report ---------------------------------------------

_FORGED_JUNIT = (
    '<testsuites><testsuite name="pytest" tests="1" failures="0" errors="0" skipped="0">'
    '<testcase classname="tests.test_mod" name="test_value"/></testsuite></testsuites>'
)
# Imported by the failing test.  It writes a passing JUnit file wherever a report could
# live: any --junitxml path and the parent's evidence dir (a sibling of the child dir
# that holds TMPDIR).  The test itself still fails.
_FORGE_REPORT_FILE = (
    "import os, sys\n"
    "from pathlib import Path\n"
    f"FORGED = {_FORGED_JUNIT!r}\n"
    "targets = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--junitxml=')]\n"
    "run = Path(os.environ['TMPDIR']).parents[1]\n"
    "targets += [str(run / 'evidence' / 'junit.xml'), str(run / 'junit.xml')]\n"
    "for target in targets:\n"
    "    try:\n"
    "        Path(target).write_text(FORGED)\n"
    "    except OSError:\n"
    "        pass\n"
    "VALUE = 3\n"
)


def test_route1_forged_junit_report_file_is_not_passed(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": _FORGE_REPORT_FILE})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert not any(a.startswith("--junitxml") for a in row["executed_argv"])
    if row["sandbox"]["sandboxed"]:
        # Seatbelt refused the write; the genuine failure is what the parent reports.
        assert row["error"] == VERIFIER_JUNIT_FAILURES, row
    else:
        # Unsandboxed the child could create the file, so the parent's O_EXCL write of
        # its own evidence refuses the planted one.
        assert row["error"] == VERIFIER_EVIDENCE_TAMPERED, row
        assert row["sandbox"]["reason"] == "no_os_barrier"


# Writes a well-formed "passed" record for the failing test into every inherited pipe,
# then lets pytest go on.  It cannot know the per-run key, so the MAC does not verify.
_FORGE_WITNESS_RECORDS = (
    "import json, os, stat\n"
    "record = {'t': 'witness', 'nodeid': 'tests/test_mod.py::test_value', 'starts': 1,\n"
    "          'returns': 1, 'unwinds': 0, 'depth': 0, 'code_file': '', 'seq': 5}\n"
    "line = ('0' * 64 + ' ' + json.dumps(record) + '\\n').encode()\n"
    "for fd in range(3, 256):\n"
    "    try:\n"
    "        if stat.S_ISFIFO(os.fstat(fd).st_mode):\n"
    "            os.write(fd, line)\n"
    "    except OSError:\n"
    "        pass\n"
    "VALUE = 3\n"
)


def test_route1_forged_records_on_the_witness_pipe_are_rejected(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": _FORGE_WITNESS_RECORDS})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_WITNESS_TAMPERED, row


# --- P1 route 2: patching pytest reporting at import ----------------------------

_PATCH_FROM_ITEM_AND_CALL = (
    "import _pytest.reports as reports\n"
    "_orig = reports.TestReport.from_item_and_call.__func__\n"
    "def _forged(cls, item, call):\n"
    "    report = _orig(cls, item, call)\n"
    "    report.outcome = 'passed'\n"
    "    report.longrepr = None\n"
    "    return report\n"
    "reports.TestReport.from_item_and_call = classmethod(_forged)\n"
    "VALUE = 3\n"
)
_PATCH_RUNTEST_NOOP = (
    "import _pytest.python\n_pytest.python.Function.runtest = lambda self: None\nVALUE = 3\n"
)
# ``TestReport.__init__`` is not in the witness's snapshot list: only the code-object
# observation can refuse this one.
_PATCH_REPORT_INIT = (
    "import _pytest.reports as reports\n"
    "_orig = reports.TestReport.__init__\n"
    "def _init(self, *args, **kwargs):\n"
    "    _orig(self, *args, **kwargs)\n"
    "    self.outcome = 'passed'\n"
    "    self.longrepr = None\n"
    "reports.TestReport.__init__ = _init\n"
    "VALUE = 3\n"
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_PATCH_FROM_ITEM_AND_CALL, VERIFIER_PYTEST_INTERNALS_PATCHED),
        (_PATCH_RUNTEST_NOOP, VERIFIER_PYTEST_INTERNALS_PATCHED),
        (_PATCH_REPORT_INIT, VERIFIER_OUTCOME_FORGED),
    ],
    ids=["from_item_and_call", "function_runtest_noop", "report_init_unsnapshotted"],
)
def test_route2_patching_pytest_reporting_at_import_is_not_passed(tmp_path, source, expected):
    root, base, cand = _repo(tmp_path, {"src_mod.py": source})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    # The forgery works on pytest itself: its exit status says every test passed.
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == expected, row
    assert row["witness"]["forged_node_ids"] == ["tests/test_mod.py::test_value"]


# --- P1 route 3: loading itself as a pytest plugin ------------------------------

_MAKEREPORT_PLUGIN = (
    "import pytest\n\n\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtest_makereport(item, call):\n"
    "    outcome = yield\n"
    "    report = outcome.get_result()\n"
    "    report.outcome = 'passed'\n"
    "    report.longrepr = None\n"
)
_DESELECT_PLUGIN = (
    "def pytest_collection_modifyitems(session, config, items):\n"
    "    items[:] = [i for i in items if i.name != 'test_value']\n"
)


@pytest.mark.parametrize(
    "plugin", [_MAKEREPORT_PLUGIN, _DESELECT_PLUGIN], ids=["makereport", "deselect"]
)
def test_route3_plugin_loaded_through_pytest_plugins_is_not_passed(tmp_path, plugin):
    test_with_plugin = (
        "pytest_plugins = ['evil_plugin_2795']\n\n"
        + _TEST_NEEDS_TWO
        + "\n\ndef test_other():\n    assert True\n"
    )
    root, base, cand = _repo(
        tmp_path, {"evil_plugin_2795.py": plugin, "tests/test_mod.py": test_with_plugin}
    )
    row = _row(
        root, base, cand, _spec("tests/test_mod.py"), ["evil_plugin_2795.py", "tests/test_mod.py"]
    )
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == VERIFIER_FOREIGN_PLUGIN, row
    assert any("evil_plugin_2795" in entry for entry in row["witness"]["foreign_plugins"])
    if plugin is _DESELECT_PLUGIN:
        assert row["witness"]["deselected_node_ids"] == ["tests/test_mod.py::test_value"]
    else:
        assert row["witness"]["forged_node_ids"] == ["tests/test_mod.py::test_value"]


def test_os_exit_before_the_session_ends_leaves_no_evidence(tmp_path):
    exits = "import atexit, os\natexit.register(lambda: None)\nos._exit(0)\n"
    root, base, cand = _repo(tmp_path, {"src_mod.py": exits})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["error"] == VERIFIER_JUNIT_MISSING
    assert row["witness"]["complete"] is False


# --- P2: skips are compared with a base run -------------------------------------

_SKIP_SOURCES = {
    "unittest_skiptest": (
        "import unittest\n\n\ndef check():\n    raise unittest.SkipTest('hidden')\n"
    ),
    "skip_exception_item_location": (
        "import pytest\n\n\ndef check():\n"
        "    raise pytest.skip.Exception('hidden', _use_item_location=True)\n"
    ),
    "partial_pytest_skip": (
        "import functools\n\nimport pytest\n\n_skip = functools.partial(pytest.skip, 'hidden')\n\n\n"
        "def check():\n    _skip()\n"
    ),
}


@pytest.mark.parametrize("route", sorted(_SKIP_SOURCES))
def test_p2_candidate_skip_on_a_node_that_passes_at_base_is_not_passed(tmp_path, route):
    root, base, cand = _repo(
        tmp_path, {"src_mod.py": _SKIP_SOURCES[route]}, base={"tests/test_keep.py": _TEST_KEEP}
    )
    row = _row(root, base, cand, _spec("tests/test_keep.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == VERIFIER_JUNIT_SKIPPED, row
    assert row["junit"]["skipped_not_at_base"] == ["tests.test_keep.test_keep"]
    assert row["junit"]["skipped_at_base"] == []
    assert row["base_run"]["ran"] is True
    assert row["base_run"]["skipped"] == []
    # The skip was raised from the untouched test file's own location: the #2794
    # touched-file attribution would have tolerated it.
    if route == "skip_exception_item_location":
        assert row["junit"]["skipped_untouched"] == ["tests.test_keep.test_keep"]


def test_p2_module_level_skip_raised_by_candidate_import_is_not_passed(tmp_path):
    source = "import unittest\n\nraise unittest.SkipTest('hidden at import')\n"
    root, base, cand = _repo(
        tmp_path, {"src_mod.py": source}, base={"tests/test_keep.py": _TEST_KEEP}
    )
    row = _row(root, base, cand, _spec("tests/test_keep.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_JUNIT_SKIPPED
    assert row["junit"]["skipped_not_at_base"] == ["tests.test_keep"]


def test_p2_skip_also_present_at_base_is_tolerated(tmp_path):
    optional = (
        "import pytest\n\n\ndef test_optional():\n"
        "    pytest.importorskip('nonexistent_mod_2795')\n\n\n"
        "def test_runs():\n    assert True\n"
    )
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n", "tests/test_optional.py": optional + "\n# touched\n"},
        base={"tests/test_optional.py": optional},
    )
    row = _row(root, base, cand, _spec("tests/test_optional.py"), ["src_mod.py", "tests"])
    assert row["passed"] is True, row
    assert row["junit"]["skipped_at_base"] == ["tests.test_optional.test_optional"]
    assert row["junit"]["skipped_not_at_base"] == []
    # Touched by the candidate, but skipped at base too: tolerated (#2794 would refuse).
    assert row["junit"]["skipped_touched"] == ["tests.test_optional.test_optional"]


def test_p2_skip_in_a_test_file_new_at_the_candidate_is_not_passed(tmp_path):
    new_test = (
        "import pytest\n\n\n@pytest.mark.skip(reason='later')\ndef test_new():\n"
        "    assert False\n\n\ndef test_ok():\n    assert True\n"
    )
    root, base, cand = _repo(tmp_path, {"tests/test_new.py": new_test})
    row = _row(root, base, cand, _spec("tests/test_new.py"), ["tests"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_JUNIT_SKIPPED
    assert row["junit"]["skipped_not_at_base"] == ["tests.test_new.test_new"]


# --- Honest candidates and the row record ---------------------------------------

_HONEST_SHAPES = """\
import asyncio
import unittest
from unittest import mock

import pytest

from src_mod import VALUE


def test_plain():
    assert VALUE == 2


@pytest.mark.parametrize("n", [1, 2])
def test_param(n):
    assert n in (1, 2)


class TestClass:
    def test_method(self):
        assert VALUE == 2


class CaseTest(unittest.TestCase):
    def test_unittest(self):
        self.assertEqual(VALUE, 2)


async def test_async():
    await asyncio.sleep(0)
    assert VALUE == 2


@mock.patch("os.getcwd", return_value="/x")
def test_patched(getcwd):
    import os
    assert os.getcwd() == "/x"


def test_tmp_path_and_raises(tmp_path):
    (tmp_path / "f.txt").write_text("ok")
    with pytest.raises(ZeroDivisionError):
        1 / 0
    try:
        raise ValueError("handled inside the test")
    except ValueError:
        pass
"""


def test_honest_candidate_with_common_test_shapes_passes(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n", "tests/test_shapes.py": _HONEST_SHAPES},
        base={"pytest.ini": "[pytest]\nasyncio_mode = auto\n"},
    )
    row = _row(root, base, cand, _spec("tests/test_shapes.py"), ["src_mod.py", "tests"])
    assert row["passed"] is True, row
    assert row["junit"]["tests"] == 8
    assert row["witness"]["forged_node_ids"] == []
    assert row["witness"]["foreign_plugins"] == []
    assert row["sandbox"]["sandboxed"] is os_sandbox_available()


def test_unsandboxed_run_is_recorded_as_not_sandboxed(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["sandbox"] == {
        "sandboxed": False,
        "barrier": None,
        "network": "not_confined",
        "reason": "no_os_barrier",
    }


def test_witness_env_keys_match_the_plugin_and_are_allow_listed():
    assert VERIFIER_WITNESS_FD_ENV == witness_plugin.WITNESS_FD_ENV
    assert VERIFIER_WITNESS_KEY_FD_ENV == witness_plugin.WITNESS_KEY_FD_ENV
    assert set(VERIFIER_WITNESS_ENV_KEYS) <= VERIFIER_ENV_ALLOWLIST
    # Imported outside a verifier (no channel), the plugin is inert.
    assert witness_plugin._WITNESS is None


def _line(key: bytes, record: dict) -> bytes:
    body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest().encode() + b" " + body + b"\n"


def test_witness_stream_rejects_bad_mac_gaps_and_partial_lines():
    key = b"k" * 32
    good = _line(key, {"t": "begin", "seq": 0}) + _line(key, {"t": "end", "seq": 1, "patched": []})
    assert _parse_witness(good, key)[0] == ""
    assert _parse_witness(good, b"x" * 32)[0] == VERIFIER_WITNESS_TAMPERED
    gap = _line(key, {"t": "begin", "seq": 0}) + _line(key, {"t": "end", "seq": 2})
    assert _parse_witness(gap, key)[0] == VERIFIER_WITNESS_TAMPERED
    assert _parse_witness(good[:-1], key)[0] == VERIFIER_WITNESS_TAMPERED


def test_witness_outcomes_need_begin_end_and_a_witnessed_return(tmp_path):
    root = tmp_path.resolve()
    (root / "tests").mkdir()
    (root / "tests/test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    common = {"root": root, "trusted_plugin_dirs": [], "deselect_allowed": False}
    assert _witness_outcomes([{"t": "begin"}], **common)[0] == VERIFIER_JUNIT_MISSING
    node = "tests/test_a.py::test_a"
    reports = [
        {"t": "report", "nodeid": node, "when": when, "outcome": "passed"}
        for when in ("setup", "call", "teardown")
    ]
    witnessed = {
        "t": "witness",
        "nodeid": node,
        "starts": 1,
        "returns": 1,
        "unwinds": 0,
        "depth": 0,
        "code_file": str(root / "tests/test_a.py"),
        "code_qualname": "test_a",
        "code_firstlineno": 1,
    }
    records = [
        {"t": "begin"},
        {"t": "item", "nodeid": node},
        {"t": "selected", "nodeids": [node]},
        *reports,
    ]
    error, cases, _ = _witness_outcomes([*records, witnessed, {"t": "end"}], **common)
    assert (error, cases) == ("", [(node, "passed", "")])
    for bad in (
        {"unwinds": 1},
        {"returns": 0},
        {"starts": 0},
        {"code_file": "/elsewhere.py"},
        {"code_qualname": "<lambda>"},
        {"code_firstlineno": 2},
    ):
        error, cases, summary = _witness_outcomes(
            [*records, {**witnessed, **bad}, {"t": "end"}], **common
        )
        assert error == VERIFIER_OUTCOME_FORGED, bad
        assert summary["forged_node_ids"] == [node]
    dropped = [*records[:2], {"t": "selected", "nodeids": []}, {"t": "end"}]
    # A dropped declared node is refused; a dropped undeclared one is only recorded.
    error, _cases, summary = _witness_outcomes(dropped, **common, declared_node_ids=[node])
    assert error == VERIFIER_TESTS_DESELECTED
    error, _cases, summary = _witness_outcomes(dropped, **common)
    assert error == ""
    assert summary["deselected_node_ids"] == [node]


# --- #2808 review round 2 -------------------------------------------------------

# Routes that swap the object pytest calls for a no-op the candidate defines.  The
# witness then sees *some* in-tree code return; only the test file's own definition
# (path, qualname, first line, read with ``ast`` by the parent) may count as a pass.
_SWAP_GETOBJ = (
    "import _pytest.python as _pp\n"
    "_noop = lambda: None\n"
    "_orig = _pp.Function._getobj\n"
    "def _getobj(self):\n"
    "    return _noop if self.name == 'test_value' else _orig(self)\n"
    "_pp.Function._getobj = _getobj\n"
    "VALUE = 3\n"
)
_SWAP_OBJ_PROPERTY = (
    "import _pytest.python as _pp\n"
    "def _noop():\n    return None\n"
    "_orig = _pp.PyobjMixin.obj\n"
    "def _obj(self):\n"
    "    return _noop if self.name == 'test_value' else _orig.fget(self)\n"
    "_pp.PyobjMixin.obj = property(_obj, _orig.fset)\n"
    "VALUE = 3\n"
)
# ``Function.__init__`` is not snapshotted: only the code-identity check refuses this.
_SWAP_OBJ_CACHE = (
    "import _pytest.python as _pp\n"
    "def _noop():\n    return None\n"
    "_orig = _pp.Function.__init__\n"
    "def _init(self, *args, **kwargs):\n"
    "    _orig(self, *args, **kwargs)\n"
    "    if self.name == 'test_value':\n"
    "        self._obj = _noop\n"
    "_pp.Function.__init__ = _init\n"
    "VALUE = 3\n"
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_SWAP_GETOBJ, VERIFIER_PYTEST_INTERNALS_PATCHED),
        (_SWAP_OBJ_PROPERTY, VERIFIER_PYTEST_INTERNALS_PATCHED),
        (_SWAP_OBJ_CACHE, VERIFIER_OUTCOME_FORGED),
    ],
    ids=["function_getobj", "pyobjmixin_obj", "obj_cache_unsnapshotted"],
)
def test_route2_swapping_the_test_object_for_an_in_tree_noop_is_not_passed(
    tmp_path, source, expected
):
    root, base, cand = _repo(tmp_path, {"src_mod.py": source})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == expected, row
    assert row["witness"]["forged_node_ids"] == ["tests/test_mod.py::test_value"]


# The #2808 reviewer's payload: rewrite the witness's emitter by attribute, then exit 0.
_EMIT_PATCH = (
    "import atexit, os, sys\n"
    "_m = sys.modules.get('_nexus_eia_verifier_witness')\n"
    "_w = getattr(_m, '_WITNESS', None)\n"
    "_ch = getattr(_w, '_channel', None)\n"
    "if _ch is not None:\n"
    "    _orig = _ch.emit\n"
    "    def _emit(rec):\n"
    "        rec = dict(rec)\n"
    "        if rec.get('t') == 'report': rec['outcome'] = 'passed'\n"
    "        if rec.get('t') == 'witness': rec.update(starts=1, returns=1, unwinds=0, depth=0)\n"
    "        _orig(rec)\n"
    "    _ch.emit = _emit\n"
    "    atexit.register(lambda: os._exit(0))\n"
    "PATCHABLE = _ch is not None\n"
    "VALUE = 3\n"
)


def test_simple_emitter_attribute_patch_no_longer_reaches_the_witness(tmp_path):
    probe = (
        "from src_mod import PATCHABLE, VALUE\n\n\n"
        "def test_value():\n    assert VALUE == 2\n\n\n"
        "def test_witness_not_reachable_by_name():\n    assert PATCHABLE is False\n"
    )
    root, base, cand = _repo(tmp_path, {"src_mod.py": _EMIT_PATCH, "tests/test_mod.py": probe})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py", "tests"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_JUNIT_FAILURES, row
    # Exactly the genuinely failing test failed: the probe test passed, i.e. the
    # module (and its emitter) was no longer importable by name.
    assert row["junit"]["failures"] == 1
    assert row["junit"]["tests"] == 2


_HELPER_PLUGIN = "import pytest\n\n\n@pytest.fixture\ndef helper_value():\n    return 2\n"
_TEST_USES_HELPER = (
    "pytest_plugins = ['helpers.fixtures_plugin']\n\n\n"
    "def test_helper(helper_value):\n    assert helper_value == 2\n"
)


def test_in_tree_helper_plugin_unchanged_since_base_is_allowed(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n"},
        base={
            "helpers/__init__.py": "",
            "helpers/fixtures_plugin.py": _HELPER_PLUGIN,
            "tests/test_helper.py": _TEST_USES_HELPER,
        },
    )
    row = _row(root, base, cand, _spec("tests/test_helper.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["foreign_plugins"] == []


def test_in_tree_helper_plugin_changed_by_the_candidate_is_foreign(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"helpers/fixtures_plugin.py": _HELPER_PLUGIN + _MAKEREPORT_PLUGIN.split("\n\n\n", 1)[1]},
        base={
            "helpers/__init__.py": "",
            "helpers/fixtures_plugin.py": _HELPER_PLUGIN,
            "tests/test_helper.py": _TEST_USES_HELPER,
        },
    )
    row = _row(root, base, cand, _spec("tests/test_helper.py"), ["helpers"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_FOREIGN_PLUGIN, row


def test_deselection_by_an_unchanged_in_tree_plugin_is_recorded_unless_declared(tmp_path):
    deselecting = "def pytest_collection_modifyitems(items):\n" + (
        "    items[:] = [i for i in items if i.name != 'test_slow']\n"
    )
    tests = (
        "pytest_plugins = ['helpers.select_plugin']\n\n\n"
        "def test_fast():\n    assert True\n\n\ndef test_slow():\n    assert True\n"
    )
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n"},
        base={
            "helpers/__init__.py": "",
            "helpers/select_plugin.py": deselecting,
            "tests/test_sel.py": tests,
        },
    )
    row = _row(root, base, cand, _spec("tests/test_sel.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["deselected_node_ids"] == ["tests/test_sel.py::test_slow"]
    declared = _row(root, base, cand, _spec("tests/test_sel.py::test_slow"), ["src_mod.py"])
    assert declared["passed"] is False
    assert declared["error"] == VERIFIER_TESTS_DESELECTED


def test_junit_names_keep_ordinary_node_names_unchanged():
    for text in ("test_value", "tests.test_mod", "test_param[1-a b]", "test_\u00e9t\u00e9[\u4e2d]"):
        assert _XML_INVALID_CHARS.sub("?", text) == text
    assert _XML_INVALID_CHARS.sub("?", "a\x00b\x1fc\ufffe") == "a?b?c?"
