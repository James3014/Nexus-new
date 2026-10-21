"""EIA closure verifier hardening follow-ups (#2811).

1. A candidate that changes a ``conftest.py`` (authorized) and drops a node of a file
   the card declares at file level is not passed (``VERIFIER_DECLARED_FILE_DESELECTED``);
   an untouched base conftest that deselects keeps the old behaviour.
2. A trusted interpreter/plugin root inside the work tree is refused with or without
   an OS sandbox, and ``pluggy`` / ``pluggy.py`` at the root are shadowing paths.
3. The configure-time writes ``pytestPDB._config`` / ``_pluginmanager`` are pinned by
   identity to the run's config and plugin manager.
4. A ``pytest``/``_pytest``/``pluggy``/``pytest_asyncio`` module first imported after the
   witness baseline (or replaced in ``sys.modules``) is never swept, so it fails closed.

Runs on Linux (unsandboxed) and macOS (sandbox-exec).
"""

from __future__ import annotations

import site
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from nexus.services.external_intelligence_closure import (
    VERIFIER_DECLARED_FILE_DESELECTED,
    VERIFIER_PYTEST_INTERNALS_PATCHED,
    VERIFIER_ROOT_SHADOWING_REFUSED,
    VERIFIER_SANDBOX_SETUP_FAILED,
    VERIFIER_TESTS_DESELECTED,
    _pytest_invocation,
    _witness_outcomes,
)
from tests.services.test_external_intelligence_closure_out_of_process_2795 import (
    _repo,
    _row,
    _spec,
)

# --- 1. authorized candidate conftest + file-level declaration ---------------------

# test_fast passes; test_slow fails unless the candidate really sets VALUE = 2.
_FAST_AND_SLOW = (
    "from src_mod import VALUE\n\n\n"
    "def test_fast():\n    assert True\n\n\n"
    "def test_slow():\n    assert VALUE == 2\n"
)
_DROP_IN_PLACE = (
    "def pytest_collection_modifyitems(items):\n"
    "    # In place, and without pytest_deselected: nothing reports the drop.\n"
    "    items[:] = [i for i in items if i.name != 'test_slow']\n"
)
_DROP_REPORTED = (
    "def pytest_collection_modifyitems(config, items):\n"
    "    dropped = [i for i in items if i.name == 'test_slow']\n"
    "    items[:] = [i for i in items if i.name != 'test_slow']\n"
    "    config.hook.pytest_deselected(items=dropped)\n"
)
_SLOW = "tests/test_sel.py::test_slow"
_PASSING = "def test_ok():\n    assert True\n"


@pytest.mark.parametrize(
    ("conftest", "target", "extra"),
    [
        (_DROP_IN_PLACE, "tests/test_sel.py", ()),
        (_DROP_REPORTED, "tests/test_sel.py", ()),
        (_DROP_IN_PLACE, "tests", ()),
        (_DROP_REPORTED, "tests/test_sel.py", ("-k", "test_")),
    ],
    ids=["in_place_drop", "reported_deselect", "directory_target", "reported_with_card_k"],
)
def test_authorized_candidate_conftest_dropping_a_declared_file_node_is_not_passed(
    tmp_path, conftest, target, extra
):
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": conftest},
        base={"tests/test_sel.py": _FAST_AND_SLOW, "tests/test_mod.py": _PASSING},
    )
    row = _row(root, base, cand, _spec(*extra, target), ["tests/conftest.py"])
    # Control: pytest itself is green, because the failing test never runs.
    assert row["returncode"] == 0
    assert row["root_shadowing_authorized_paths"] == ["tests/conftest.py"]
    assert row["passed"] is False
    assert row["error"] == VERIFIER_DECLARED_FILE_DESELECTED, row
    assert row["witness"]["declared_file_deselected_node_ids"] == [_SLOW]


def test_untouched_base_conftest_that_deselects_keeps_the_old_behaviour(tmp_path):
    passing = _FAST_AND_SLOW.replace("assert VALUE == 2", "assert True")
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n"},
        base={"tests/conftest.py": _DROP_IN_PLACE, "tests/test_sel.py": passing},
    )
    row = _row(root, base, cand, _spec("tests/test_sel.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["deselected_node_ids"] == [_SLOW]
    assert row["witness"]["declared_file_deselected_node_ids"] == []


def _drop_records(selected: list[str], collected: list[str]) -> list[dict]:
    reports = [
        {"t": "report", "nodeid": n, "when": when, "outcome": outcome}
        for n in selected
        for when, outcome in (("setup", "passed"), ("call", "failed"), ("teardown", "passed"))
    ]
    return [
        {"t": "begin"},
        *({"t": "item", "nodeid": n} for n in collected),
        {"t": "selected", "nodeids": selected},
        *reports,
        {"t": "end"},
    ]


def test_declared_file_rule_only_covers_declared_files_and_needs_a_changed_conftest(tmp_path):
    root = tmp_path.resolve()
    common = {"root": root, "trusted_plugin_dirs": [], "deselect_allowed": False}
    kept, dropped = "tests/test_a.py::test_one", "tests/test_b.py::test_two"
    records = _drop_records([kept], [kept, dropped])
    # Undeclared file: recorded only, even with a changed conftest.
    error, _cases, summary = _witness_outcomes(
        records, **common, declared_paths=["tests/test_a.py"], conftest_changed=True
    )
    assert error == ""
    assert summary["deselected_node_ids"] == [dropped]
    assert summary["declared_file_deselected_node_ids"] == []
    # Declared (also as an absolute path or with a trailing slash on its directory).
    for declared in (["tests/test_b.py"], [str(root / "tests/test_b.py")], ["tests/"], ["."]):
        error, _cases, summary = _witness_outcomes(
            records, **common, declared_paths=declared, conftest_changed=True
        )
        assert error == VERIFIER_DECLARED_FILE_DESELECTED, declared
        assert summary["declared_file_deselected_node_ids"] == [dropped]
    # No positional target at all: the whole configured run is declared.
    error, _cases, _summary = _witness_outcomes(records, **common, conftest_changed=True)
    assert error == VERIFIER_DECLARED_FILE_DESELECTED
    # Only node ids declared: the existing node rule applies, not the file rule.
    error, _cases, _summary = _witness_outcomes(
        records, **common, declared_node_ids=[kept], conftest_changed=True
    )
    assert error == ""
    error, _cases, _summary = _witness_outcomes(
        records, **common, declared_node_ids=[dropped], conftest_changed=True
    )
    assert error == VERIFIER_TESTS_DESELECTED
    # No conftest in the candidate diff: unchanged behaviour.
    error, _cases, _summary = _witness_outcomes(
        records, **common, declared_paths=["tests/test_b.py"], conftest_changed=False
    )
    assert error == ""


def test_invocation_records_positional_file_targets():
    invocation = _pytest_invocation(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-k",
            "expr",
            "-p",
            "no:cacheprovider",
            "tests/test_a.py",
            "tests/test_b.py::test_two",
            "tests/sub/",
        ],
        "",
    )
    assert invocation.declared_paths == ("tests/test_a.py", "tests/sub/")
    assert invocation.declared_node_ids == ("tests/test_b.py::test_two",)


# --- 2. trusted roots inside the work tree; pluggy shadowing ------------------------


def _in_tree_venv(root: Path) -> Path:
    """A venv inside the work tree (ignored by git) that imports this interpreter's
    packages through a ``.pth`` line, so pytest resolves outside the tree but the
    interpreter prefix is inside it."""
    venv = root / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120
    )
    purelib = sysconfig.get_path("purelib", vars={"base": str(venv), "platbase": str(venv)})
    lines = "".join(f"import site; site.addsitedir({p!r})\n" for p in site.getsitepackages())
    Path(purelib, "outer_2811.pth").write_text(lines, encoding="utf-8")
    return venv / "bin" / "python"


@pytest.mark.parametrize("os_sandbox", [True, False], ids=["os_sandbox", "no_os_sandbox"])
def test_trusted_interpreter_root_inside_the_work_tree_is_refused(
    tmp_path, monkeypatch, os_sandbox
):
    if not os_sandbox:
        monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")
    root, base, cand = _repo(
        tmp_path, {"src_mod.py": "VALUE = 2\n"}, base={".gitignore": ".venv/\n"}
    )
    python = _in_tree_venv(root)
    # The interpreter itself resolves outside the tree, so only the prefix check refuses.
    assert not python.resolve().is_relative_to(root)
    spec = {"id": "pytest", "argv": [str(python), "-m", "pytest", "-q", "tests/test_mod.py"]}
    row = _row(root, base, cand, spec, ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_SANDBOX_SETUP_FAILED, row


@pytest.mark.parametrize("path", ["pluggy.py", "pluggy/__init__.py", "Pluggy.py"])
def test_root_pluggy_is_a_shadowing_path(tmp_path, path):
    files = {"src_mod.py": "VALUE = 2\n", path: "X = 1\n"}
    root, base, cand = _repo(tmp_path, files)
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_ROOT_SHADOWING_REFUSED, row
    assert row["root_shadowing_refused_paths"] == [path]
    authorized = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py", path])
    assert authorized["root_shadowing_authorized_paths"] == [path]


# --- 3. configure-time writes pinned by identity -------------------------------------


@pytest.mark.parametrize("attr", ["_config", "_pluginmanager"])
def test_configure_time_pdb_write_of_another_value_is_patched(tmp_path, attr):
    conftest = (
        "from _pytest.debugging import pytestPDB\n\n\n"
        "def pytest_sessionstart(session):\n"
        f"    pytestPDB.{attr} = object()\n"
    )
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n", "conftest.py": conftest})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py", "conftest.py"])
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert f"_pytest.debugging:pytestPDB.{attr}" in row["witness"]["pytest_internals_patched"]


def test_debugging_plugin_disabled_leaves_the_pinned_values_unchanged_and_passes(tmp_path):
    root, base, cand = _repo(tmp_path, {"src_mod.py": "VALUE = 2\n"})
    row = _row(root, base, cand, _spec("-p", "no:debugging", "tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["pytest_internals_patched"] == []


# --- 4. late-imported pytest/_pytest/pluggy/pytest_asyncio modules ------------------

# Not loaded at the baseline (only the pytester plugin imports it).  The candidate
# imports it at collection and swaps a function's code: nothing swept it.
_LATE_SUBMODULE_SWAP = (
    "import _pytest.pytester_assertions as _pa\n"
    "def _noop(*args, **kwargs):\n"
    "    return None\n"
    "_pa.assert_outcomes.__code__ = _noop.__code__\n"
    "VALUE = 2\n"
)
_FAKE_SUBMODULE = (
    "import sys, types\n"
    "sys.modules['_pytest.nexus_fake_2811'] = types.ModuleType('_pytest.nexus_fake_2811')\n"
    "VALUE = 2\n"
)
_REPLACED_MODULE = (
    "import sys, types\n"
    "sys.modules['pluggy._tracing'] = types.ModuleType('pluggy._tracing')\n"
    "VALUE = 2\n"
)


@pytest.mark.parametrize(
    ("source", "marker"),
    [
        (_LATE_SUBMODULE_SWAP, "late_module:_pytest.pytester_assertions"),
        (_FAKE_SUBMODULE, "late_module:_pytest.nexus_fake_2811"),
        (_REPLACED_MODULE, "module_replaced:pluggy._tracing"),
    ],
    ids=["late_submodule_code_swap", "fake_submodule", "replaced_module"],
)
def test_module_first_imported_after_the_baseline_is_patched(tmp_path, source, marker):
    root, base, cand = _repo(tmp_path, {"src_mod.py": source})
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["returncode"] == 0
    assert row["passed"] is False
    assert row["error"] == VERIFIER_PYTEST_INTERNALS_PATCHED, row
    assert marker in row["witness"]["pytest_internals_patched"], row["witness"]


def test_honest_run_imports_no_late_pytest_module(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n"},
        base={"pytest.ini": "[pytest]\nasyncio_mode = auto\n", "conftest.py": "import os\n"},
    )
    row = _row(root, base, cand, _spec("tests/test_mod.py"), ["src_mod.py"])
    assert row["passed"] is True, row
    assert row["witness"]["pytest_internals_patched"] == []
