"""#2948: a candidate-added target after a long option the verifier cannot classify statically.

``--full-trace tests/test_new.py tests/test_mod.py`` with a changed conftest used to fail the
base ``--collect-only`` run (``VERIFIER_BASE_RUN_FAILED``): the added file was kept as the
option's possible value, and does not exist at base. The base run now drops it like any
target missing at base, and keeps that only when the base run's own parser reports the
option takes no value. Otherwise the option would swallow the next target, so the base run
is repeated with the token kept as its value, as before.
"""

from __future__ import annotations

from types import SimpleNamespace

from nexus.services.external_intelligence_closure import VERIFIER_DECLARED_NODE_MISSING
from nexus.services.external_intelligence_verifier_witness import _long_option_arity
from tests.services.test_eia_closure_verifier_followups_2811 import (
    _DROP_AT_MAKEITEM,
    _FAST_AND_SLOW,
    _PASSING,
)
from tests.services.test_external_intelligence_closure_out_of_process_2795 import (
    _repo,
    _row,
    _spec,
)

_FIXTURE_CONFTEST = "import pytest\n\n\n@pytest.fixture\ndef extra():\n    return 1\n"
_VALUE_SEED = "def pytest_addoption(parser):\n    parser.addoption('--seed-file')\n"


def test_the_issue_repro_with_full_trace_passes(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/conftest.py": _FIXTURE_CONFTEST,
            "src_mod.py": "VALUE = 2\n",
            "tests/test_new.py": _PASSING,
        },
    )
    spec = _spec("--full-trace", "tests/test_new.py", "tests/test_mod.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py", "src_mod.py", "tests/test_new.py"])
    assert row["passed"] is True, row
    assert row["base_collect"]["options_with_dropped_token"] == ["--full-trace"], row


def test_a_full_trace_card_still_refuses_a_dropped_test(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": _DROP_AT_MAKEITEM, "tests/test_new.py": _PASSING},
        base={"tests/test_sel.py": _FAST_AND_SLOW, "tests/test_mod.py": _PASSING},
    )
    spec = _spec("--full-trace", "tests/test_new.py", "tests/test_sel.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py", "tests/test_new.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_DECLARED_NODE_MISSING, row


def test_a_value_option_at_base_keeps_its_token_and_still_refuses_a_dropped_test(tmp_path):
    # The base conftest gives "--seed-file" a value. Dropping "seed.txt" would let it swallow
    # tests/test_sel.py at base, so test_slow's drop would escape; the base parser says it
    # takes a value, so the token is kept with it.
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/conftest.py": _VALUE_SEED + "\n\n" + _DROP_AT_MAKEITEM,
            "src_mod.py": "VALUE = 2\n",
            "seed.txt": "1\n",
        },
        base={
            "tests/conftest.py": _VALUE_SEED,
            "tests/test_sel.py": _FAST_AND_SLOW,
            "tests/test_mod.py": _PASSING,
        },
    )
    spec = _spec("--seed-file", "seed.txt", "tests/test_sel.py", "tests/test_mod.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py", "src_mod.py", "seed.txt"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_DECLARED_NODE_MISSING, row
    assert row["base_collect"]["options_with_dropped_token"] == [], row


def test_a_node_id_after_a_value_option_does_not_hide_a_dropped_test(tmp_path):
    # #2948 review: a node id right after "--seed-file" was left out of the base run before its
    # option was considered, so "--seed-file" swallowed tests/test_sel.py there and
    # test_slow's drop escaped (the node id itself is still observed through its file).
    root, base, cand = _repo(
        tmp_path,
        {
            "tests/conftest.py": _VALUE_SEED + "\n\n" + _DROP_AT_MAKEITEM,
            "src_mod.py": "VALUE = 2\n",
        },
        base={
            "tests/conftest.py": _VALUE_SEED,
            "tests/test_sel.py": _FAST_AND_SLOW,
            "tests/test_mod.py": _PASSING,
        },
    )
    spec = _spec(
        "--seed-file", "tests/test_mod.py::test_ok", "tests/test_sel.py", "tests/test_mod.py"
    )
    row = _row(root, base, cand, spec, ["tests/conftest.py", "src_mod.py"])
    assert row["passed"] is False
    assert row["error"] == VERIFIER_DECLARED_NODE_MISSING, row


def test_a_value_option_at_base_still_passes_an_honest_card(tmp_path):
    root, base, cand = _repo(
        tmp_path,
        {"tests/conftest.py": _VALUE_SEED + "\n\n" + _FIXTURE_CONFTEST, "seed.txt": "1\n"},
        base={"tests/conftest.py": _VALUE_SEED, "tests/test_mod.py": _PASSING},
    )
    spec = _spec("--seed-file", "seed.txt", "tests/test_mod.py")
    row = _row(root, base, cand, spec, ["tests/conftest.py", "seed.txt"])
    assert row["passed"] is True, row


def test_the_witness_reports_how_the_parser_reads_each_long_option():
    from _pytest.config import _prepareconfig

    config = _prepareconfig(["--full-trace", "--durations", "5", "--maxfail=2", "-x", "a.py"])
    assert _long_option_arity(config) == {
        "--full-trace": 0,
        "--durations": "None",
        "--maxfail": "None",
    }
    # An unreadable parser reads as "unknown" (the option is left out), never as no value.
    assert _long_option_arity(SimpleNamespace()) == {}
