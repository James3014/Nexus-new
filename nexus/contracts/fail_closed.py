"""Fail-closed status decision helper (#2454).

One small rule, shared: a status allows progress only when it is a string that is
*exactly* one of the caller's declared success values. Everything else blocks --
missing, malformed, indeterminate ("unknown", "abstain", "not executed", still
running, ...) and simply unrecognised values alike.

This generalises a family of escapes in which an indeterminate outcome was read
as a pass:

* #2069 -- the committee passed with no verified winner (every verifier refused
  with ``not_executed:no_os_barrier``, or the round abstained); fixed by #2077.
* #1504 -- an unknown/unresolved provider outcome was treated as terminal success.
* #1542 -- an unrecognised status string fell through to the success branch.

Matching is exact and case-sensitive. Case is never normalised: ``"verified"`` is
not ``"VERIFIED"``. The module is stdlib-only so any layer can import it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "INDETERMINATE_PREFIXES",
    "INDETERMINATE_STATES",
    "Decision",
    "DecisionResult",
    "decide",
    "decide_all",
    "is_indeterminate",
]


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    status: object
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


INDETERMINATE_STATES: frozenset[str] = frozenset({
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
})

# Any status with one of these prefixes is indeterminate (e.g. "not_executed:no_os_barrier").
INDETERMINATE_PREFIXES: tuple[str, ...] = ("not_executed:",)


def is_indeterminate(status: str) -> bool:
    """True when *status* names an indeterminate outcome (exact, case-sensitive)."""
    return status in INDETERMINATE_STATES or status.startswith(INDETERMINATE_PREFIXES)


def _validate_success(success: object) -> frozenset[str]:
    if not isinstance(success, frozenset):
        raise ValueError("success must be a frozenset of status strings")
    if not success:
        raise ValueError("success must not be empty")
    for member in success:
        if not isinstance(member, str) or not member:
            raise ValueError(f"success members must be non-empty strings: {member!r}")
        if is_indeterminate(member):
            raise ValueError(f"success must not contain an indeterminate status: {member!r}")
    return success


def _as_text(status: object) -> str | None:
    if isinstance(status, Enum):
        value = status.value
        return value if isinstance(status, str) and isinstance(value, str) else None
    if isinstance(status, str):
        return str.__str__(status)
    return None


def decide(status: object, *, success: frozenset[str]) -> DecisionResult:
    """Return ALLOW only when *status* is exactly one of *success*; otherwise BLOCK.

    Reasons on BLOCK: ``MISSING`` (None or empty), ``MALFORMED`` (not a str or str
    Enum), ``INDETERMINATE:<s>`` or ``UNRECOGNISED:<s>``. On ALLOW the reason is
    ``SUCCESS:<s>``. Raises ValueError when *success* is not a non-empty frozenset
    of determinate status strings.
    """
    _validate_success(success)
    if status is None:
        return DecisionResult(Decision.BLOCK, status, "MISSING")
    text = _as_text(status)
    if text is None:
        return DecisionResult(Decision.BLOCK, status, "MALFORMED")
    if text == "":
        return DecisionResult(Decision.BLOCK, status, "MISSING")
    if text in success:
        return DecisionResult(Decision.ALLOW, status, f"SUCCESS:{text}")
    if is_indeterminate(text):
        return DecisionResult(Decision.BLOCK, status, f"INDETERMINATE:{text}")
    return DecisionResult(Decision.BLOCK, status, f"UNRECOGNISED:{text}")


def decide_all(statuses: Iterable[object], *, success: frozenset[str]) -> DecisionResult:
    """ALLOW only when *statuses* is non-empty and every status is ALLOW.

    The first blocking status decides the reason; an empty input blocks as ``MISSING``.
    """
    _validate_success(success)
    items = list(statuses)
    if not items:
        return DecisionResult(Decision.BLOCK, tuple(items), "MISSING")
    for status in items:
        result = decide(status, success=success)
        if result.decision is not Decision.ALLOW:
            return result
    return DecisionResult(Decision.ALLOW, tuple(items), "SUCCESS:ALL")
