"""#2454: table-driven contract for nexus.contracts.fail_closed."""

from __future__ import annotations

from enum import Enum

import pytest

from nexus.contracts.fail_closed import (
    INDETERMINATE_STATES,
    Decision,
    DecisionResult,
    decide,
    decide_all,
)

_SUCCESS = frozenset({"VERIFIED", "COMPLETED"})

_EXPECTED_INDETERMINATE = {
    "UNKNOWN",
    "OUTCOME_UNKNOWN",
    "ABSTAIN",
    "NO_WINNER",
    "NOT_EXECUTED",
    "NOT_RUN",
    "MISSING",
    "MALFORMED",
    "ERROR",
    "TIMEOUT",
    "RUNNING",
    "QUEUED",
    "PENDING",
    "WAITING_INPUT",
}


class _StrStatus(str, Enum):
    VERIFIED = "VERIFIED"
    RUNNING = "RUNNING"


class _PlainStatus(Enum):
    VERIFIED = "VERIFIED"


def test_indeterminate_set_is_exactly_the_documented_states() -> None:
    assert isinstance(INDETERMINATE_STATES, frozenset)
    assert set(INDETERMINATE_STATES) == _EXPECTED_INDETERMINATE


_BLOCK_CASES: list[tuple[object, str]] = [
    *[(state, f"INDETERMINATE:{state}") for state in sorted(_EXPECTED_INDETERMINATE)],
    ("not_executed:no_os_barrier", "INDETERMINATE:not_executed:no_os_barrier"),
    ("not_executed:command_not_allowed", "INDETERMINATE:not_executed:command_not_allowed"),
    (None, "MISSING"),
    ("", "MISSING"),
    (0, "MALFORMED"),
    (1, "MALFORMED"),
    (True, "MALFORMED"),
    (False, "MALFORMED"),
    (b"VERIFIED", "MALFORMED"),
    (["VERIFIED"], "MALFORMED"),
    (_PlainStatus.VERIFIED, "MALFORMED"),
    (_StrStatus.RUNNING, "INDETERMINATE:RUNNING"),
    ("verified", "UNRECOGNISED:verified"),
    ("Verified", "UNRECOGNISED:Verified"),
    (" VERIFIED", "UNRECOGNISED: VERIFIED"),
    ("VERIFIED ", "UNRECOGNISED:VERIFIED "),
    ("running", "UNRECOGNISED:running"),
    ("NOT_EXECUTED:no_os_barrier", "UNRECOGNISED:NOT_EXECUTED:no_os_barrier"),
    ("PASSED", "UNRECOGNISED:PASSED"),
]


@pytest.mark.parametrize(("status", "reason"), _BLOCK_CASES, ids=repr)
def test_blocking_statuses(status: object, reason: str) -> None:
    result = decide(status, success=_SUCCESS)
    assert result.decision is Decision.BLOCK
    assert result.reason == reason
    assert result.allowed is False


def test_object_instance_blocks_as_malformed() -> None:
    result = decide(object(), success=_SUCCESS)
    assert result.decision is Decision.BLOCK
    assert result.reason == "MALFORMED"


@pytest.mark.parametrize(
    ("status", "text"),
    [("VERIFIED", "VERIFIED"), ("COMPLETED", "COMPLETED"), (_StrStatus.VERIFIED, "VERIFIED")],
)
def test_exact_success_member_allows(status: object, text: str) -> None:
    result = decide(status, success=_SUCCESS)
    assert result == DecisionResult(Decision.ALLOW, status, f"SUCCESS:{text}")
    assert result.allowed is True


def test_str_subclass_is_compared_by_value() -> None:
    class _Text(str):
        pass

    assert decide(_Text("VERIFIED"), success=_SUCCESS).decision is Decision.ALLOW
    assert decide(_Text("verified"), success=_SUCCESS).decision is Decision.BLOCK


@pytest.mark.parametrize(
    "bad",
    [
        frozenset(),
        {"VERIFIED"},
        ["VERIFIED"],
        ("VERIFIED",),
        "VERIFIED",
        None,
        frozenset({"VERIFIED", "UNKNOWN"}),
        frozenset({"ABSTAIN"}),
        frozenset({"not_executed:no_os_barrier"}),
        frozenset({"VERIFIED", ""}),
        frozenset({"VERIFIED", 1}),
    ],
    ids=repr,
)
def test_bad_success_set_raises(bad: object) -> None:
    with pytest.raises(ValueError):
        decide("VERIFIED", success=bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        decide_all(["VERIFIED"], success=bad)  # type: ignore[arg-type]


def test_decide_all_empty_blocks() -> None:
    result = decide_all([], success=_SUCCESS)
    assert result.decision is Decision.BLOCK
    assert result.reason == "MISSING"
    assert decide_all(iter(()), success=_SUCCESS).decision is Decision.BLOCK


def test_decide_all_requires_every_status() -> None:
    assert decide_all(["VERIFIED", "COMPLETED"], success=_SUCCESS).decision is Decision.ALLOW
    mixed = decide_all(["VERIFIED", "ABSTAIN", "nope"], success=_SUCCESS)
    assert mixed.decision is Decision.BLOCK
    assert mixed.reason == "INDETERMINATE:ABSTAIN"
    assert decide_all(["VERIFIED", None], success=_SUCCESS).reason == "MISSING"
    assert decide_all(("VERIFIED", "verified"), success=_SUCCESS).decision is Decision.BLOCK


def test_decision_result_is_frozen() -> None:
    result = decide("VERIFIED", success=_SUCCESS)
    with pytest.raises(AttributeError):
        result.decision = Decision.BLOCK  # type: ignore[misc]
