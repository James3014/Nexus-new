"""``--strict-llm-baseline`` semantics for the same-model A/B lane (issue #1820).

Legacy ADRs (teacher-student sweep plan, route-cost measurement lessons) require
that a success with ``model_calls == 0`` is not counted as a model solve: it came
from a deterministic/local rescue path. Under strict mode such rows are tagged
``solve_classification="deterministic_rescue"`` and reported separately.

Replay note (wiring plan PR-1): a capability receipt is real only if its boundaries say so.
The unified-capability overlay (``nexus/research/flow/unified_capability_projection.py``)
re-projects ``receipt_base.claim_boundary`` to real only when the runtime stage carries
``simulated=False``, ``receipt_present=True`` and evidence refs sealed in the capability's own
``REAL_INVOKED`` evidence-bundle entry; refs resolving only through the executor's own record
are reported as ``real_self_reported``.  Bench rows recorded before that rule (e.g. ``runs_20261014b``) carry none of
these, so replaying them through the overlay classifies those capabilities simulated by design;
regenerate the numbers from a fresh run instead of loosening the rule.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

WITH_NEXUS_MODE = "with_nexus"
WITHOUT_NEXUS_MODE = "without_nexus"
SOLVE_WITHOUT_CAPABILITY = "solve_without_capability"
DETERMINISTIC_RESCUE = "deterministic_rescue"
# A with-Nexus SUCCESS that a model call preceded but Nexus's local path delivered
# (``local_preflight`` / ``local_hidden_shadow`` / ...): not a model solve.
LOCAL_RESCUE = "rescued_by_local"
# A with-Nexus SUCCESS reached only after the bench showed the arm the hidden verifier's
# failure (deterministic hidden pre-retry or a model retry quoting the hidden test, R1).
# The bare arm never gets that feedback, so it is never a model solve.
HIDDEN_FEEDBACK_RESCUE = "rescued_by_hidden_feedback"
HIDDEN_FEEDBACK_RETRY_REASONS = frozenset({
    "hidden_verifier_failure_deterministic_pre_retry",
    "hidden_verifier_failure_bounded_nexus_retry",
})
MODEL_SOLVE = "model_solve"
# Treatment lane (wiring plan PR-3): a with-Nexus SUCCESS whose delivered candidate is a LATER model
# candidate of the row (self-heal, candidate pool). Counts in ``after_treatment`` only, never in
# ``first_attempt``; the first candidate is scored separately (``first_attempt_hidden_passed``).
TREATMENT_MODEL_SOLVE = "treatment_model_solve"
LANE_TREATMENT = "treatment"
LANE_SCORECARD_SCHEMA = "online_ab_lane_scorecard_v1"
# Receipt class for a selected planner node with no executable body (control-plane reference,
# routing node): reported apart from ``selected_not_invoked``; never real, never simulated.
NOT_EXECUTABLE = "NOT_EXECUTABLE"
NOT_EXECUTABLE_CLASS = "not_executable"
# Receipt class for an invocation whose executor reports it ran but whose evidence the runtime
# did not seal (set by the unified-capability overlay): never real, never simulated.
REAL_SELF_REPORTED_CLASS = "real_self_reported"
# Receipt class for an executor that started and refused for missing inputs (set by the
# overlay with ``blocked_reason``): the capability did not run; never real, never simulated.
BLOCKED_MISSING_INPUTS_CLASS = "blocked_missing_inputs"
# Started and did not succeed for any other reason (refusal / failure code recorded): visible,
# never real, never simulated.
FAILED_OR_REFUSED_CLASS = "failed_or_refused"
# A SUCCESS reached by a bounded Hyper re-run after the first attempt failed (Nexus treatment).
NEXUS_TREATMENT_RESCUE = "rescued_by_nexus_treatment"
# The run's captured-prompt symmetry audit failed or errored: no row of it is a solve of any kind.
PROMPT_SYMMETRY_VIOLATION = "prompt_symmetry_violation"
# A task x trial pair cut by an early stop: excluded from both arms' denominators symmetrically.
NOT_RUN = "not_run"
# Winner sources that name the model; any other non-empty source is a local/deterministic delivery.
MODEL_WINNER_PREFIXES = ("llm", "model", "nexus_llm", "direct_")
NON_MODEL_WINNER_SOURCES = frozenset({"nexus_llm_deterministic_pre_rescue"})
NOT_SOLVED = "not_solved"
RECEIPT_DATA_CONTRACT_VIOLATION = "receipt_data_contract_violation"
SCORECARD_SCHEMA = "strict_v2_honest_scorecard_v1"


def _model_calls(row: dict[str, Any]) -> int:
    try:
        return int(row.get("model_calls") or 0)
    except (TypeError, ValueError):
        return 0


def local_delivery(row: dict[str, Any]) -> bool:
    """True when Nexus's local/deterministic path, not the model, delivered the result.

    Allowlist, not denylist: only ``llm*`` / ``model*`` / ``nexus_llm*`` / ``direct_*`` (the bare
    provider path) winner sources (minus
    ``nexus_llm_deterministic_pre_rescue``) are model deliveries; ``deterministic_local``,
    ``verification_only`` or any other named source is local.  An empty source (the bare arm,
    legacy rows) is not treated as local.
    """

    if row.get("local_success_source") is True:
        return True
    source = str(row.get("nexus_winner_source") or "").strip().lower()
    if not source:
        return False
    if source in NON_MODEL_WINNER_SOURCES:
        return True
    return not source.startswith(MODEL_WINNER_PREFIXES)


def hidden_feedback_used(row: dict[str, Any]) -> bool:
    """True when the delivered result came after hidden-verifier feedback (R1)."""

    return (
        row.get("hidden_retry_used") is True
        or str(row.get("hidden_retry_reason") or "") in HIDDEN_FEEDBACK_RETRY_REASONS
    )


def receipt_contract_violation(row: dict[str, Any]) -> bool:
    return (
        str(row.get("infra_invalid_reason") or "") == RECEIPT_DATA_CONTRACT_VIOLATION
        or str(row.get("receipt_data_contract_status") or "").lower() == "infra_invalid"
    )


def apply_strict_llm_baseline_classification(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tag finished rows in place; only a model-delivered SUCCESS is a model solve.

    * SUCCESS with no model call -> ``deterministic_rescue`` (#1820).
    * SUCCESS only after hidden-verifier feedback (``hidden_retry_used`` / a feedback
      ``hidden_retry_reason``) -> with-Nexus: ``rescued_by_hidden_feedback``; bare: ``not_solved``.
    * SUCCESS after a model call but delivered by Nexus's local path -> with-Nexus:
      ``rescued_by_local``; bare arm: ``not_solved`` (the bare arm has no Nexus path, so a
      local delivery there is never credited).
    * A with-Nexus ``receipt_data_contract_violation`` is flagged as a wiring defect.
    """

    for row in rows:
        row["strict_llm_baseline_applied"] = True
        mode = str(row.get("mode", ""))
        row["rescued_by_local"] = False
        if row.get("not_run"):
            row["solve_classification"] = NOT_RUN
            row["deterministic_rescue"] = False
        elif row.get("prompt_symmetry_violation"):
            row["solve_classification"] = PROMPT_SYMMETRY_VIOLATION
            row["deterministic_rescue"] = False
        elif (
            row.get("status") != "SUCCESS"
            or str(row.get("infra_invalid_reason") or "") == "task_stop_loss_exceeded"
        ):
            # S16: a stop-loss overrun is a failure that stays in the denominator, both arms.
            row["solve_classification"] = NOT_SOLVED
            row["deterministic_rescue"] = False
        else:
            is_rescue = _model_calls(row) <= 0
            row["deterministic_rescue"] = is_rescue
            if is_rescue:
                row["solve_classification"] = DETERMINISTIC_RESCUE
            elif hidden_feedback_used(row):
                row["hidden_feedback_rescue"] = True
                if mode == WITH_NEXUS_MODE:
                    row["solve_classification"] = HIDDEN_FEEDBACK_RESCUE
                    row["rescued_by_local"] = True
                else:
                    row["solve_classification"] = NOT_SOLVED
            elif row.get("bounded_nexus_rescue_used") is True:
                # L4: a bounded Hyper re-run is Nexus treatment, never the first attempt's solve.
                if mode == WITH_NEXUS_MODE:
                    row["solve_classification"] = NEXUS_TREATMENT_RESCUE
                    row["rescued_by_local"] = True
                else:
                    row["solve_classification"] = NOT_SOLVED
            elif local_delivery(row):
                if mode == WITH_NEXUS_MODE:
                    row["solve_classification"] = LOCAL_RESCUE
                    row["rescued_by_local"] = True
                else:
                    row["solve_classification"] = NOT_SOLVED
                    row["bare_local_delivery_rejected"] = True
            elif mode == WITH_NEXUS_MODE and row.get("lane") == LANE_TREATMENT:
                row["solve_classification"] = _treatment_lane_solve(row)
            else:
                row["solve_classification"] = MODEL_SOLVE
        apply_lane_columns(row)
        if mode == WITH_NEXUS_MODE and receipt_contract_violation(row):
            row["wiring_defect"] = RECEIPT_DATA_CONTRACT_VIOLATION
        if mode == WITH_NEXUS_MODE:
            classify_row_capabilities(row)
    return rows


# Only these first-attempt statuses mean the runner scored call 1's own model candidate.
FIRST_ATTEMPT_VERIFIED = frozenset({"verified_as_delivered", "verified_confined_rescore"})


def _treatment_lane_solve(row: dict[str, Any]) -> str:
    """A treatment-lane with-Nexus SUCCESS, bound to the RUNNER-derived model candidates.

    The delivered sha must be one the runner re-derived from a captured model response and the
    row must not be unverifiable (a product sha with no captured origin). ``model_solve`` only
    when that is call 1's stage-1 candidate; any later candidate is ``treatment_model_solve``.
    """

    final = str(row.get("final_model_candidate_sha256") or row.get("model_candidate_sha256") or "")
    runner = [str(item) for item in row.get("runner_candidate_sha256s") or []]
    kinds = [str(item) for item in row.get("runner_candidate_kinds") or []]
    if (
        not final
        or final not in runner
        or row.get("final_candidate_in_model_candidates") is not True
        or row.get("treatment_unverifiable") is True
    ):
        row["treatment_sha_unbound"] = True
        return NOT_SOLVED
    if row.get("treatment_round_void") is True:
        return NOT_SOLVED  # a later round carried hidden text (R2-3): the row is void, not a solve
    if runner[0] == final and kinds[:1] == ["stage1"]:
        return MODEL_SOLVE  # call 1's own candidate was delivered: a first-attempt solve
    return TREATMENT_MODEL_SOLVE


def _int(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            value = int(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value:
            return value
    return 0


def apply_lane_columns(row: dict[str, Any]) -> dict[str, Any]:
    """Per-row ``first_attempt`` / ``after_treatment`` (bool, None for not_run) plus cost columns.

    Strict lane and the bare arm: both columns are the strict model solve. Treatment-lane
    with-Nexus rows: ``first_attempt`` is the hidden test on the FIRST model candidate's bytes
    (same verifier as the strict lane) and ``after_treatment`` the delivered candidate's
    classification. A prompt-symmetry violation or hidden feedback voids both.
    """

    row["tokens"] = _int(row, "tokens", "total_tokens", "model_total_tokens")
    row.setdefault("treatment_applied", [])
    classification = row.get("solve_classification")
    if row.get("not_run"):
        row["first_attempt"] = None
        row["after_treatment"] = None
        return row
    if row.get("lane") != LANE_TREATMENT or str(row.get("mode", "")) != WITH_NEXUS_MODE:
        solved = classification == MODEL_SOLVE
        row["first_attempt"] = solved
        row["after_treatment"] = solved
        return row
    void = (
        classification == PROMPT_SYMMETRY_VIOLATION
        or bool(row.get("prompt_symmetry_violation"))
        or hidden_feedback_used(row)
        or row.get("bounded_nexus_rescue_used") is True
    )
    row["first_attempt"] = bool(
        not void
        and _model_calls(row) > 0
        and row.get("first_model_candidate_sha256")
        and row.get("first_attempt_status") in FIRST_ATTEMPT_VERIFIED
        and row.get("first_attempt_hidden_passed") is True
    )
    row["after_treatment"] = bool(
        not void
        and row.get("treatment_unverifiable") is not True
        and row.get("treatment_round_void") is not True
        and classification in {MODEL_SOLVE, TREATMENT_MODEL_SOLVE}
    )
    return row


def lane_scorecard(rows: Iterable[dict[str, Any]], mode: str) -> dict[str, Any]:
    """``first_attempt`` and ``after_treatment`` solves for one arm, with cost (all-rows denominator)."""

    arm = [r for r in rows if str(r.get("mode", "")) == mode and not r.get("not_run")]
    lanes = sorted({str(r.get("lane") or "strict") for r in arm})
    first = sum(1 for r in arm if r.get("first_attempt") is True)
    after = sum(1 for r in arm if r.get("after_treatment") is True)
    calls = sum(_model_calls(r) for r in arm)
    tokens = sum(_int(r, "tokens", "total_tokens", "model_total_tokens") for r in arm)
    first_calls = sum(min(1, _model_calls(r)) for r in arm)
    gain = after - first
    applied: dict[str, int] = {}
    for row in arm:
        for name in row.get("treatment_applied") or []:
            applied[str(name)] = applied.get(str(name), 0) + 1
    total = len(arm)
    return {
        "schema": LANE_SCORECARD_SCHEMA,
        "lanes": lanes,
        "total_n": total,
        "first_attempt": first,
        "after_treatment": after,
        "treatment_gain": gain,
        "first_attempt_rate": round(first / total, 4) if total else None,
        "after_treatment_rate": round(after / total, 4) if total else None,
        "model_calls_total": calls,
        "extra_model_calls": calls - first_calls,
        "tokens_total": tokens,
        "tokens_per_extra_solve": round(tokens / gain, 1) if gain > 0 else None,
        "treatment_applied": dict(sorted(applied.items())),
        "treatment_sha_unbound_n": sum(1 for r in arm if r.get("treatment_sha_unbound")),
        "first_attempt_unverified_n": sum(
            1
            for r in arm
            if r.get("lane") == LANE_TREATMENT
            and mode == WITH_NEXUS_MODE
            and _model_calls(r) > 0
            and r.get("first_attempt_hidden_passed") is None
        ),
    }


def honest_scorecard(rows: Iterable[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Per-arm scorecard over ALL rows of ``mode`` (nothing is dropped from the denominator).

    ``solved_by_model + rescued_by_local + failed == total_n``.  ``rescued_by_local`` is
    always 0 for the bare arm (its deterministic rescues count as failed: no model solve and
    no Nexus).  ``contract_violation`` (with-Nexus receipt data contract violations, a wiring
    defect) and ``infra_invalid`` are reported alongside, not removed.
    """

    arm = [r for r in rows if str(r.get("mode", "")) == mode and not r.get("not_run")]
    solved = [r for r in arm if r.get("solve_classification") == MODEL_SOLVE]
    if mode == WITH_NEXUS_MODE:
        rescued = [
            r
            for r in arm
            if r.get("solve_classification")
            in {LOCAL_RESCUE, DETERMINISTIC_RESCUE, HIDDEN_FEEDBACK_RESCUE, NEXUS_TREATMENT_RESCUE}
        ]
    else:
        rescued = []
    total = len(arm)
    treatment_solved = [r for r in arm if r.get("solve_classification") == TREATMENT_MODEL_SOLVE]
    violations = [r for r in arm if mode == WITH_NEXUS_MODE and receipt_contract_violation(r)]
    return {
        "schema": SCORECARD_SCHEMA,
        "total_n": total,
        "solved_by_model": len(solved),
        "rescued_by_local": len(rescued),
        # Treatment lane only (0 in the strict lane): solved by a later model candidate.
        "solved_by_model_after_treatment": len(treatment_solved),
        "failed": total - len(solved) - len(rescued) - len(treatment_solved),
        "contract_violation": len(violations),
        "contract_violation_failed": sum(1 for r in violations if r.get("status") != "SUCCESS"),
        "infra_invalid": sum(1 for r in arm if r.get("infra_invalid_reason")),
        "model_solve_rate_all_rows": round(len(solved) / total, 4) if total else None,
        "wiring_defects": sorted({
            str(r.get("wiring_defect")) for r in violations if r.get("wiring_defect")
        }),
    }


def _claim_boundary(receipt: dict[str, Any]) -> dict[str, Any] | None:
    """Return the receipt's effective claim_boundary mapping, or None when it carries none.

    A receipt can carry two boundaries: ``receipt_base.claim_boundary`` and the top-level
    ``claim_boundary`` (the runtime stage's, set by the unified-capability overlay).  When
    both exist the stricter one wins: the result is ``simulated=False`` only when both say
    exactly ``False`` (tighten-only, wiring plan PR-1).
    """

    base = receipt.get("receipt_base")
    rb_cb = (
        base["claim_boundary"]
        if isinstance(base, dict) and isinstance(base.get("claim_boundary"), dict)
        else None
    )
    top_cb = receipt["claim_boundary"] if isinstance(receipt.get("claim_boundary"), dict) else None
    if rb_cb is None or top_cb is None:
        return rb_cb if rb_cb is not None else top_cb
    simulated = not (
        rb_cb.get("simulated", True) is False and top_cb.get("simulated", True) is False
    )
    merged = {**top_cb, **rb_cb, "simulated": simulated}
    if simulated:
        merged["claim_eligible"] = False
    return merged


def is_not_executable(receipt: dict[str, Any]) -> bool:
    """True for an explicit ``NOT_EXECUTABLE:<class>`` receipt (planner node with no body)."""

    if bool(receipt.get("invoked")):
        return False
    return (
        receipt.get("not_executable") is True
        or str(receipt.get("execution_state") or "") == NOT_EXECUTABLE
        or str(receipt.get("failure_reason") or "").startswith(f"{NOT_EXECUTABLE}:")
    )


def classify_receipt(receipt: dict[str, Any]) -> str:
    """Return ``real``, ``simulated``, ``selected_not_invoked`` or ``not_executable``.

    ``real``: invoked, ``attestation == "real"`` (written by the unified-capability overlay),
    ``claim_boundary.simulated`` is not true, and ``evidence_refs`` is non-empty; the same
    without that attestation is ``real_self_reported``.
    A receipt that carries no claim_boundary at all (runner-synthesized telemetry backfill or
    deterministic receipt-lite entries) attests nothing: with evidence refs it is
    ``real_self_reported`` (never ``real``; also listed under ``capabilities_real_unattested`` so
    it stays visible), without refs ``simulated``.
    ``selected_not_invoked``: selected by the planner but never invoked.
    Everything else invoked (simulated=true, or no evidence) is ``simulated``.
    ``not_executable``: an explicit ``NOT_EXECUTABLE:<class>`` receipt (nothing could run).
    ``blocked_missing_inputs``: the executor started and refused for missing inputs.
    ``failed_or_refused``: the executor started and did not succeed for another reason.
    ``real_self_reported``: the overlay found every runtime signal consistent but the evidence
    refs resolve only through the executor's own record (no runtime-sealed evidence).
    """

    if is_not_executable(receipt):
        return NOT_EXECUTABLE_CLASS
    if not bool(receipt.get("invoked")):
        return "selected_not_invoked"
    if str(receipt.get("attestation") or "") == BLOCKED_MISSING_INPUTS_CLASS:
        return BLOCKED_MISSING_INPUTS_CLASS
    if str(receipt.get("attestation") or "") == FAILED_OR_REFUSED_CLASS:
        return FAILED_OR_REFUSED_CLASS
    if str(receipt.get("attestation") or "") == REAL_SELF_REPORTED_CLASS:
        has_refs = bool([ref for ref in (receipt.get("evidence_refs") or []) if str(ref).strip()])
        return REAL_SELF_REPORTED_CLASS if has_refs else "simulated"
    if str(receipt.get("attestation") or "") == "simulated":
        return "simulated"
    boundary = _claim_boundary(receipt)
    has_refs = bool([ref for ref in (receipt.get("evidence_refs") or []) if str(ref).strip()])
    if boundary is None:
        # No boundary at all attests nothing: never real, never in the real tally or uplift.
        return REAL_SELF_REPORTED_CLASS if has_refs else "simulated"
    simulated = boundary.get("simulated", True) is not False
    if simulated or not has_refs:
        return "simulated"
    # Real only when the unified-capability overlay attested it; a non-simulated boundary
    # without that attestation is the receipt's own claim (Gemini review of #2212, G2).
    return "real" if _overlay_attested_real(receipt) else REAL_SELF_REPORTED_CLASS


def _overlay_attested_real(receipt: dict[str, Any]) -> bool:
    """``attestation=real`` together with the overlay's own markers (Gemini r2 N3).

    A consistency marker written by ``unified_capability_projection``, not a signature: row
    JSON is produced by the bench runner, and a hand-edited row can still forge it.
    """

    disposition = receipt.get("attestation_disposition")
    return (
        str(receipt.get("attestation") or "") == "real"
        and receipt.get("attestation_source") == "unified_capability_projection"
        and receipt.get("attestation_refs_resolved") is True
        and isinstance(disposition, dict)
        and disposition.get("kind") == "succeeded"
    )


def classify_row_capabilities(row: dict[str, Any]) -> dict[str, Any]:
    """Split a with-Nexus row's capability receipts; set ``capability_not_exercised`` in place."""

    real: list[str] = []
    unattested: list[str] = []
    simulated: list[str] = []
    not_invoked: list[str] = []
    not_executable: list[str] = []
    self_reported: list[str] = []
    blocked: dict[str, str] = {}
    failed: dict[str, str] = {}
    for receipt in row.get("capability_receipts") or []:
        if not isinstance(receipt, dict) or not receipt.get("selected", True):
            continue
        name = str(receipt.get("name") or "")
        kind = classify_receipt(receipt)
        if kind == "real":
            real.append(name)
        elif kind == "simulated":
            simulated.append(name)
        elif kind == NOT_EXECUTABLE_CLASS:
            not_executable.append(name)
        elif kind == REAL_SELF_REPORTED_CLASS:
            self_reported.append(name)
            if str(receipt.get("attestation") or "") != "real_self_reported":
                unattested.append(name)  # no runtime attestation; visibility only
        elif kind == BLOCKED_MISSING_INPUTS_CLASS:
            blocked[name] = str(receipt.get("blocked_reason") or "unspecified")
        elif kind == FAILED_OR_REFUSED_CLASS:
            failed[name] = str(receipt.get("blocked_reason") or "unspecified")
        else:
            not_invoked.append(name)
    row["capabilities_real"] = sorted(set(real))
    row["capabilities_real_unattested"] = sorted(set(unattested) - set(real))
    row["capabilities_simulated"] = sorted(set(simulated) - set(real))
    row["capabilities_selected_not_invoked"] = sorted(set(not_invoked) - set(real) - set(simulated))
    row["capabilities_real_self_reported"] = sorted(set(self_reported) - set(real))
    row["capabilities_blocked_missing_inputs"] = sorted(set(blocked) - set(real))
    row["capability_blocked_reasons"] = {
        name: blocked[name] for name in row["capabilities_blocked_missing_inputs"]
    }
    row["capabilities_failed_or_refused"] = sorted(set(failed) - set(real))
    row["capability_failed_reasons"] = {
        name: failed[name] for name in row["capabilities_failed_or_refused"]
    }
    row["capabilities_not_executable"] = sorted(
        set(not_executable) - set(real) - set(simulated) - set(not_invoked)
    )
    row["capability_not_exercised"] = not row["capabilities_real"]
    row["solve_without_capability"] = bool(
        row.get("solve_classification") == MODEL_SOLVE and row["capability_not_exercised"]
    )
    return row


def capability_tally(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per-capability ``{real, simulated, selected_not_invoked}`` over classified with-Nexus rows."""

    tally: dict[str, dict[str, int]] = {}
    for row in rows:
        for key, field in (
            ("real", "capabilities_real"),
            ("simulated", "capabilities_simulated"),
            ("selected_not_invoked", "capabilities_selected_not_invoked"),
        ):
            for name in row.get(field) or []:
                entry = tally.setdefault(
                    name, {"real": 0, "simulated": 0, "selected_not_invoked": 0}
                )
                entry[key] += 1
    return dict(sorted(tally.items()))


def not_executable_tally(
    rows: Iterable[dict[str, Any]], *, field: str = "capabilities_not_executable"
) -> dict[str, int]:
    """Per-capability count of a separately reported receipt class (default NOT_EXECUTABLE)."""

    tally: dict[str, int] = {}
    for row in rows:
        for name in row.get(field) or []:
            tally[name] = tally.get(name, 0) + 1
    return dict(sorted(tally.items()))


def blocked_missing_inputs_tally(
    rows: Iterable[dict[str, Any]], *, field: str = "capability_blocked_reasons"
) -> dict[str, dict[str, int]]:
    """Per-capability ``{reason_code: count}`` for a reason-carrying class (default blocked)."""

    tally: dict[str, dict[str, int]] = {}
    for row in rows:
        for name, reason in (row.get(field) or {}).items():
            entry = tally.setdefault(name, {})
            entry[reason] = entry.get(reason, 0) + 1
    return {name: dict(sorted(v.items())) for name, v in sorted(tally.items())}


def capability_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Strict capability-exercise figures for the with-Nexus rows of one arm."""

    classified = [r for r in rows if "capability_not_exercised" in r]
    eligible = [r for r in classified if bool(r.get("run_eligible", True))]
    solves = [r for r in eligible if r.get("solve_classification") == MODEL_SOLVE]
    uplift = [r for r in solves if not r["capability_not_exercised"]]
    return {
        "capability_rows_n": len(classified),
        "real_capability_rows_n": sum(1 for r in classified if not r["capability_not_exercised"]),
        "attested_real_capability_rows_n": sum(
            1
            for r in classified
            if set(r.get("capabilities_real") or [])
            - set(r.get("capabilities_real_unattested") or [])
        ),
        "simulated_only_rows_n": sum(
            1
            for r in classified
            if r["capability_not_exercised"] and r.get("capabilities_simulated")
        ),
        "capability_not_exercised_rows_n": sum(
            1 for r in classified if r["capability_not_exercised"]
        ),
        "capability_tally": capability_tally(classified),
        "capability_not_executable_tally": not_executable_tally(classified),
        "capability_blocked_missing_inputs": blocked_missing_inputs_tally(classified),
        "capability_failed_or_refused": blocked_missing_inputs_tally(
            classified, field="capability_failed_reasons"
        ),
        "capability_real_self_reported_tally": not_executable_tally(
            classified, field="capabilities_real_self_reported"
        ),
        "solves_with_real_capability_n": len(uplift),
        "solve_without_capability_n": len(solves) - len(uplift),
        "nexus_uplift_solved_n": len(uplift),
        "nexus_uplift_solve_rate": round(len(uplift) / len(eligible), 4) if eligible else None,
    }


def apply_strict_llm_baseline_to_summary(
    rows: list[dict[str, Any]],
    summary: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Recompute solve counts per arm so deterministic rescues are not solves.

    S16: the denominator is every row of the arm. ESCALATE (no model call) and stop-loss rows are
    failures, never removed as ineligible; ``run_eligible_n`` is reported alongside.
    """

    for mode, arm in summary.items():
        eligible = [
            row for row in rows if str(row.get("mode", "")) == mode and not row.get("not_run")
        ]
        arm["run_eligible_n"] = sum(1 for row in eligible if bool(row.get("run_eligible", True)))
        arm["unpaired_completed_n"] = sum(
            1 for row in rows if str(row.get("mode", "")) == mode and row.get("unpaired_completed")
        )
        arm["not_run_n"] = sum(
            1 for row in rows if str(row.get("mode", "")) == mode and row.get("not_run")
        )
        solved = [row for row in eligible if row.get("solve_classification") == MODEL_SOLVE]
        first_pass = [row for row in solved if int(row.get("attempt_count", 0) or 0) <= 1]
        arm["strict_llm_baseline_applied"] = True
        arm["solved_n"] = len(solved)
        arm["deterministic_rescue_n"] = sum(
            1 for row in eligible if row.get("deterministic_rescue") is True
        )
        arm["scorecard"] = honest_scorecard(rows, mode)
        arm["lane_scorecard"] = lane_scorecard(rows, mode)
        arm["solve_rate"] = round(len(solved) / len(eligible), 4) if eligible else None
        arm["first_pass_rate"] = round(len(first_pass) / len(eligible), 4) if eligible else None
        if mode == WITH_NEXUS_MODE:
            arm.update(
                capability_summary([row for row in rows if str(row.get("mode", "")) == mode])
            )
    return summary


def reclassify_report_dir(report_dir: str | Path) -> dict[str, Any]:
    """Re-read ``*.jsonl`` rows of an existing report dir and compute strict tallies."""

    root = Path(report_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict) and "mode" in row:
                    rows.append(row)
    apply_strict_llm_baseline_classification(rows)
    by_mode: dict[str, dict[str, Any]] = {}
    for mode in sorted({str(r.get("mode", "")) for r in rows}):
        by_mode[mode] = {"rows_n": sum(1 for r in rows if str(r.get("mode", "")) == mode)}
    apply_strict_llm_baseline_to_summary(rows, by_mode)
    per_row = [
        {
            "task_id": r.get("task_id"),
            "status": r.get("status"),
            "model_calls": _model_calls(r),
            "solve_classification": r.get("solve_classification"),
            "first_attempt": r.get("first_attempt"),
            "after_treatment": r.get("after_treatment"),
            "tokens": r.get("tokens"),
            "treatment_applied": r.get("treatment_applied"),
            "wiring_defect": r.get("wiring_defect"),
            "capabilities_real": r.get("capabilities_real"),
            "capabilities_real_unattested": r.get("capabilities_real_unattested"),
            "capabilities_simulated": r.get("capabilities_simulated"),
            "capabilities_not_executable": r.get("capabilities_not_executable"),
            "capabilities_real_self_reported": r.get("capabilities_real_self_reported"),
            "capability_blocked_reasons": r.get("capability_blocked_reasons"),
            "capability_failed_reasons": r.get("capability_failed_reasons"),
            "capability_not_exercised": r.get("capability_not_exercised"),
        }
        for r in rows
        if str(r.get("mode", "")) == WITH_NEXUS_MODE
    ]
    return {"report_dir": str(root), "arms": by_mode, "with_nexus_rows": per_row}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-read a bench report dir with strict capability tallies."
    )
    parser.add_argument("--reclassify", metavar="REPORT_DIR", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(reclassify_report_dir(args.reclassify), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
