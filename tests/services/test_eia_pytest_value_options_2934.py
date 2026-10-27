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
    _base_collect_invocation,
    _pytest_invocation,
)
from tests.services.test_eia_closure_verifier_followups_2811 import (
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
    if isinstance(invocation, str):  # refused: fails closed
        return
    assert invocation is not None
    assert invocation.declared_paths == ()
    assert invocation.declared_node_ids == ()


def test_a_real_target_after_an_unknown_value_option_is_still_declared():
    argv = [sys.executable, "-m", "pytest", "--durations", "5", "tests/test_sel.py"]
    invocation = _pytest_invocation(argv, _PATH)
    if isinstance(invocation, str):  # refused: fails closed
        return
    assert invocation is not None
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
    ("args", "paths"),
    [
        (("--random-order-seed", "5"), ()),
        (("--random-order-seed", "5", "tests/test_sel.py"), ("tests/test_sel.py",)),
        (("--durations=5", "tests/test_sel.py"), ("tests/test_sel.py",)),
        (("--lf", "tests/test_sel.py"), ("tests/test_sel.py",)),
        (("--strict-markers", "tests"), ("tests",)),
        (("--unknown-flag", "-k", "fast"), ()),
        (("-q", "tests/test_sel.py"), ("tests/test_sel.py",)),
    ],
    ids=[
        "unknown_long",
        "unknown_long_then_target",
        "equals",
        "known_flag",
        "strict_markers",
        "unknown_then_dash",
        "short_flag",
    ],
)
def test_unknown_long_options_never_turn_their_value_into_a_target(args, paths):
    assert _invocation(*args).declared_paths == paths


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
