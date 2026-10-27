"""#2934: the value of a pytest option the parser does not know is not a declared path.

``--durations 5`` used to record ``5`` as a positional file target, so a card that names
no real target was treated as file-scoped and a changed ``conftest.py`` that drops tests
was no longer refused. The parser must fail closed: either refuse the invocation (an
error code) or keep the value out of ``declared_paths``.
"""

from __future__ import annotations

import os
import sys

import pytest

from nexus.services.external_intelligence_closure import (
    VERIFIER_BASE_RUN_FAILED,
    VERIFIER_DECLARED_NODE_MISSING,
    _base_collect_invocation,
    _pytest_invocation,
    _with_pytest_options,
)
from tests.services.test_eia_closure_verifier_followups_2811 import (
    _DROP_AT_MAKEITEM,
    _DROP_IN_PLACE,
    _FAST_AND_SLOW,
    _PASSING,
)
from tests.services.test_external_intelligence_closure_out_of_process_2795 import (
    _repo,
    _row,
    _spec,
)

_PATH = os.environ.get("PATH", "")


@pytest.mark.parametrize(
    "options",
    [
        ("--durations", "5"),
        ("--log-level", "INFO"),
        ("-n", "4"),
        ("--cov", "src"),
        ("--timeout", "30"),
    ],
    ids=["durations", "log_level", "xdist_n", "cov", "timeout"],
)
def test_an_unknown_value_option_value_is_not_a_declared_path(options):
    invocation = _pytest_invocation([sys.executable, "-m", "pytest", "-q", *options], _PATH)
    assert not isinstance(invocation, str) and invocation is not None
    assert invocation.declared_paths == ()
    assert invocation.declared_node_ids == ()


def test_a_real_target_after_an_unknown_value_option_is_still_declared():
    argv = [sys.executable, "-m", "pytest", "--durations", "5", "tests/test_sel.py"]
    invocation = _pytest_invocation(argv, _PATH)
    assert not isinstance(invocation, str) and invocation is not None
    assert "tests/test_sel.py" in invocation.declared_paths
    assert "5" not in invocation.declared_paths


def test_known_value_options_and_node_ids_keep_working():
    argv = [sys.executable, "-m", "pytest", "-k", "fast", "tests/test_sel.py::test_fast"]
    invocation = _pytest_invocation(argv, _PATH)
    assert not isinstance(invocation, str) and invocation is not None
    assert invocation.declared_paths == ()
    assert invocation.declared_node_ids == ("tests/test_sel.py::test_fast",)


@pytest.mark.parametrize("extra", [("--durations", "5"), ()], ids=["durations", "plain"])
def test_a_changed_conftest_dropping_tests_is_not_passed_with_a_value_option(tmp_path, extra):
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": _DROP_IN_PLACE},
        base={"tests/test_sel.py": _FAST_AND_SLOW, "tests/test_mod.py": _PASSING},
    )
    row = _row(root, base, cand, _spec(*extra), ["tests/conftest.py"])
    if not extra:  # control: pytest itself is green, because the failing test never runs
        assert row["returncode"] == 0, row
    assert row["passed"] is False, row
    assert row["error"], row


def _invocation(*args):
    invocation = _pytest_invocation([sys.executable, "-m", "pytest", *args], _PATH)
    assert not isinstance(invocation, str) and invocation is not None
    return invocation


@pytest.mark.parametrize(
    ("args", "paths", "nodes"),
    [
        (("--random-order-seed", "5"), (), ()),
        (("--random-order-seed", "5", "a.py"), ("5", "a.py"), ()),
        (("--full-trace", "a.py", "b.py"), ("a.py", "b.py"), ()),
        (("--runslow", "a.py", "b.py"), ("a.py", "b.py"), ()),
        (("--full-trace", "a.py", "b.py::t"), ("a.py",), ("b.py::t",)),
        (("--lf", "a.py"), (), ()),
        (("--durations=5", "a.py"), ("a.py",), ()),
        (("--unknown-flag", "-k", "fast"), (), ()),
        (("--", "a.py", "b.py"), ("a.py", "b.py"), ()),
        (("-xk", "fast"), (), ()),
        (("-qp", "no:cacheprovider", "a.py"), ("a.py",), ()),
        (("-pno:cacheprovider", "a.py"), ("a.py",), ()),
        (("-q", "a.py"), ("a.py",), ()),
    ],
    ids=[
        "unknown_long_only",
        "unknown_long_then_target",
        "unknown_flag_keeps_both_targets",
        "plugin_flag_keeps_both_targets",
        "unknown_flag_keeps_target_before_node",
        "lone_ambiguous_target_is_whole_run",
        "equals",
        "unknown_then_dash",
        "double_dash",
        "grouped_short_value",
        "grouped_short_value_then_target",
        "attached_short_value",
        "short_flag",
    ],
)
def test_an_option_value_never_narrows_or_invents_targets(args, paths, nodes):
    invocation = _invocation(*args)
    assert invocation.declared_paths == paths
    assert invocation.declared_node_ids == nodes


def test_a_flag_before_two_targets_keeps_both_refused(tmp_path):
    # Opus review of #2934: "--full-trace a b" swallowed a, so a dropped node of a escaped.
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": _DROP_IN_PLACE},
        base={"tests/test_sel.py": _FAST_AND_SLOW, "tests/test_mod.py": _PASSING},
    )
    spec = _spec("--full-trace", "tests/test_sel.py", "tests/test_mod.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py"])
    assert row["passed"] is False, row


def test_base_collect_keeps_an_unknown_option_value_with_its_option(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sel.py").write_text("def test_ok():\n    assert True\n")
    invocation = _invocation("--random-order-seed", "5", "tests/test_sel.py")
    collected = _base_collect_invocation(invocation, tmp_path, tmp_path)
    assert collected is not None
    assert collected.pytest_args == (
        "--random-order-seed",
        "5",
        "tests/test_sel.py",
        "--collect-only",
    )


def test_verifier_options_go_before_a_double_dash():
    # Codex review of #2934: after "--" pytest reads every token as a target, an appended
    # "-c" or "--collect-only" included.
    assert _with_pytest_options(("-q", "--", "a.py"), "-p", "x") == ("-q", "-p", "x", "--", "a.py")
    assert _with_pytest_options(("-q", "a.py"), "-p", "x") == ("-q", "a.py", "-p", "x")


def test_base_collect_keeps_collect_only_an_option_after_a_double_dash(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sel.py").write_text("def test_ok():\n    assert True\n")
    collected = _base_collect_invocation(_invocation("--", "tests/test_sel.py"), tmp_path, tmp_path)
    assert collected is not None
    assert collected.pytest_args == ("--collect-only", "--", "tests/test_sel.py")


def test_a_card_with_a_double_dash_runs_under_the_verifier_options(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"tests/test_ok.py": _PASSING + "\n\ndef test_two():\n    assert True\n"},
        base={"tests/test_ok.py": _PASSING},
    )
    row = _row(root, base, cand, _spec("--", "tests/test_ok.py"), ["tests/test_ok.py"])
    assert row["passed"] is True, row


def test_a_double_dash_card_dropping_tests_is_refused(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": _DROP_IN_PLACE},
        base={"tests/test_sel.py": _FAST_AND_SLOW, "tests/test_mod.py": _PASSING},
    )
    spec = _spec("--", "tests/test_sel.py", "tests/test_mod.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py"])
    assert row["passed"] is False, row


_FIXTURE_CONFTEST = "import pytest\n\n\n@pytest.fixture\ndef extra():\n    return 1\n"


def test_a_candidate_added_target_after_a_flag_is_not_a_base_run_failure(tmp_path):
    # #2948: the added file was kept as the flag's value, so the base run got a path that
    # does not exist there and failed (VERIFIER_BASE_RUN_FAILED).
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/conftest.py": _FIXTURE_CONFTEST,
            "src_mod.py": "VALUE = 2\n",
            "tests/test_new.py": _PASSING,
        },
    )
    authorized = ["tests/conftest.py", "src_mod.py", "tests/test_new.py"]
    for flag in ((), ("--full-trace",)):
        spec = _spec(*flag, "tests/test_new.py", "tests/test_mod.py")
        row = _row(root, base, cand, spec, authorized)
        assert row["passed"] is True, (flag, row)


def test_a_candidate_added_target_after_a_flag_still_refuses_a_dropped_test(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": _DROP_AT_MAKEITEM, "tests/test_new.py": _PASSING},
        base={"tests/test_sel.py": _FAST_AND_SLOW, "tests/test_mod.py": _PASSING},
    )
    spec = _spec("--full-trace", "tests/test_new.py", "tests/test_sel.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py", "tests/test_new.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_DECLARED_NODE_MISSING, row


def test_base_collect_moves_the_flag_before_an_added_target_last(tmp_path):
    base_tree, root = tmp_path / "base", tmp_path / "cand"
    for tree in (base_tree, root):
        (tree / "tests").mkdir(parents=True)
        (tree / "tests" / "test_sel.py").write_text(_PASSING)
    (root / "tests" / "test_new.py").write_text(_PASSING)
    invocation = _invocation("--full-trace", "tests/test_new.py", "tests/test_sel.py")
    collected = _base_collect_invocation(invocation, base_tree, root)
    assert collected is not None
    assert collected.pytest_args == ("tests/test_sel.py", "--collect-only", "--full-trace")


_VALUE_OPTION_CONFTEST = "def pytest_addoption(parser):\n    parser.addoption('--seed-file')\n"


def test_a_value_option_whose_value_the_candidate_added_does_not_swallow_a_target(tmp_path):
    # If "--seed-file" kept its place after its value was dropped, the base run would read
    # tests/test_sel.py as the value, compare test_mod.py only and miss the dropped test.
    # Moved last, it has no value at base and the base run fails: a refusal either way.
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/conftest.py": _VALUE_OPTION_CONFTEST + "\n\n" + _DROP_AT_MAKEITEM,
            "seed.txt": "1\n",
        },
        base={
            "tests/conftest.py": _VALUE_OPTION_CONFTEST,
            "tests/test_sel.py": _FAST_AND_SLOW,
            "tests/test_mod.py": _PASSING,
        },
    )
    spec = _spec("--seed-file", "seed.txt", "tests/test_sel.py", "tests/test_mod.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py", "seed.txt"])
    assert row["passed"] is False
    assert row["error"] in (VERIFIER_BASE_RUN_FAILED, VERIFIER_DECLARED_NODE_MISSING), row
