"""Product-side hooks for the online A/B "treatment" lane (wiring plan PR-3).

The counted A/B has two lanes. The strict lane (``NEXUS_SYMMETRIC_PROMPT=1``) allows exactly one
model call per row. The treatment lane keeps the same symmetric prompt, but
``NEXUS_BENCH_TREATMENT_LANE=1`` lets the product run its own treatments in the with-Nexus arm:
visible-test self-heal, several stage-1 candidates. Only the bench runner sets these variables.

This module gives the sprint three things:

* ``treatment_lane_active``: the lane switch. It is only honoured together with the symmetric
  prompt, so it can never turn treatments on outside the audited A/B.
* ``record_model_candidate``: every raw model candidate the sprint produces in symmetric mode is
  recorded by sha256, in order. The research flow delivers only a recorded candidate; the bench
  does NOT trust this list: it re-derives every candidate from the prompt-capture wrapper's own
  record of each model response and accepts the product's list only where it matches.
* ``row_deadline_allows_round``: one wall-clock deadline for the whole row. A treatment round
  starts only with at least one full per-call cap left, so later rounds never extend the row's
  budget and a round is never cut off by the row deadline.
* ``record_failed_model_call``: a model call that produced no candidate is recorded as a
  placeholder (sha ``None``), so the first entry always belongs to the first call.
* ``treatment_round_allowed``: the deadline check plus the row's model-call budget
  (``NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS``); a round that would exceed either never starts.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import MutableMapping
from typing import Any

TREATMENT_LANE_ENV = "NEXUS_BENCH_TREATMENT_LANE"
ROW_DEADLINE_ENV = "NEXUS_BENCH_ROW_DEADLINE_EPOCH"
ROUND_MIN_REMAINING_ENV = "NEXUS_BENCH_ROUND_MIN_REMAINING_SEC"
MAX_MODEL_CALLS_ENV = "NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS"
# Without an explicit minimum, a new round needs a full per-call cap left (the gateway timeout the
# runner gives both arms); without that, a conservative 300 s.
DEFAULT_ROUND_MIN_REMAINING_SEC = 300.0
PER_CALL_CAP_ENV = "NEXUS_GATEWAY_TIMEOUT_SEC"
# Product labels of a stage-1 model candidate (the first attempt can only be one of these).
STAGE1_MODEL_SOURCES = frozenset({"llm", "nexus_llm_baseline", "llm_assisted"})
FAILED_CALL_SOURCE = "llm_failed"
# learning_trace keys (read by the bench through the hyper-sprint report's learning_trace).
SHA_LIST_KEY = "model_candidate_sha256s"
SOURCE_LIST_KEY = "model_candidate_sources"
FIRST_SHA_KEY = "first_model_candidate_sha256"
SKIPPED_ROUNDS_KEY = "treatment_rounds_skipped_row_deadline"
BUDGET_SKIPPED_KEY = "treatment_rounds_skipped_call_budget"
_TRUE = {"1", "true", "yes"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def treatment_lane_active() -> bool:
    """True only in the bench treatment lane: the lane flag AND the symmetric prompt."""

    return _flag(TREATMENT_LANE_ENV) and _flag("NEXUS_SYMMETRIC_PROMPT")


def candidate_sha256(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def is_stage1_model_source(source: str) -> bool:
    return str(source or "").strip().lower() in STAGE1_MODEL_SOURCES


def record_model_candidate(trace: MutableMapping[str, Any], code: str, source: str) -> str:
    """Append one raw model candidate (sha256 + source label) to the sprint's learning trace."""

    if not isinstance(code, str) or not code:
        return ""
    sha = candidate_sha256(code)
    shas = trace.setdefault(SHA_LIST_KEY, [])
    sources = trace.setdefault(SOURCE_LIST_KEY, [])
    shas.append(sha)
    sources.append(str(source or ""))
    trace.setdefault(FIRST_SHA_KEY, sha)
    return sha


def record_failed_model_call(
    trace: MutableMapping[str, Any], source: str = FAILED_CALL_SOURCE
) -> None:
    """A model call that produced no model candidate (no patch, parse error, refusal...).

    Keeps the list aligned with the calls: the first attempt is bound to the FIRST call, so a
    failed first call leaves ``first_attempt`` unsolved whatever later rounds deliver.
    """

    trace.setdefault(SHA_LIST_KEY, []).append(None)
    trace.setdefault(SOURCE_LIST_KEY, []).append(str(source or FAILED_CALL_SOURCE))
    trace.setdefault(FIRST_SHA_KEY, None)


def row_deadline_remaining_sec(now: float | None = None) -> float | None:
    raw = os.environ.get(ROW_DEADLINE_ENV, "").strip()
    if not raw:
        return None
    try:
        deadline = float(raw)
    except ValueError:
        return 0.0  # unparseable deadline: fail closed (no further round)
    return deadline - (time.time() if now is None else now)


def row_deadline_allows_round(
    trace: MutableMapping[str, Any], stage: str, *, now: float | None = None
) -> bool:
    """False when a new treatment round would start with less than the minimum time left."""

    remaining = row_deadline_remaining_sec(now)
    if remaining is None:
        return True
    try:
        minimum = float(
            os.environ.get(ROUND_MIN_REMAINING_ENV, "")
            or os.environ.get(PER_CALL_CAP_ENV, "")
            or DEFAULT_ROUND_MIN_REMAINING_SEC
        )
    except ValueError:
        minimum = DEFAULT_ROUND_MIN_REMAINING_SEC
    if remaining >= minimum:
        return True
    trace.setdefault(SKIPPED_ROUNDS_KEY, []).append(stage)
    return False


def model_call_budget_allows(
    trace: MutableMapping[str, Any], stage: str, model_calls_so_far: int
) -> bool:
    raw = os.environ.get(MAX_MODEL_CALLS_ENV, "").strip()
    if not raw:
        return True
    try:
        budget = int(raw)
    except ValueError:
        budget = 1  # unparseable budget: fail closed (first call only)
    if int(model_calls_so_far) < max(1, budget):
        return True
    trace.setdefault(BUDGET_SKIPPED_KEY, []).append(stage)
    return False


def treatment_round_allowed(
    trace: MutableMapping[str, Any], stage: str, model_calls_so_far: int
) -> bool:
    """A further model round in the treatment lane: inside the row deadline and call budget."""

    return model_call_budget_allows(trace, stage, model_calls_so_far) and row_deadline_allows_round(
        trace, stage
    )
