"""Bench "treatment" lane for the online A/B (wiring plan PR-3).

The strict lane (default) scores one model call per row on identical prompts. The treatment lane
keeps every information-fairness rule of the strict lane and only turns the product's own
treatments on for the with-Nexus arm:

* kept (both lanes): no hidden-test feedback, no task hints, deterministic/local deliveries never
  count as a model solve, the same model and account leasing, the same per-call cap, one shared row
  deadline, ABBA interleave, and the captured-prompt symmetry audit (every call, not only the
  first one, see ``prompt_symmetry_audit.audit_treatment_round``);
* turned on (with-Nexus arm only): visible-test self-heal, several stage-1 candidates (the hyper
  candidate pool, capped by ``--treatment-max-model-calls``), the ultra_review route gate and the
  committee switch. DayShift stage 2 stays off: it calls a different model.

Each with-Nexus row then carries two outcomes:

* ``first_attempt``: the first model candidate, scored exactly like the strict lane (the hidden
  test on those exact bytes, put back in the target file after the row ended);
* ``after_treatment``: the delivered (final) candidate, which must be one of the row's recorded
  model candidates.

The bare arm is the strict lane's bare arm (one call): its ``after_treatment`` is its first attempt.
``--bare-retries`` exists so the choice is explicit and recorded; only 0 is supported.

``treatment_applied`` lists treatments that are attested, not self-reported: a capability receipt
classified ``real`` by ``strict_llm_baseline.classify_receipt``, or for self-heal / several
candidates the prompt-capture wrapper's own count of calls, which must match the product's record.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

LANE_STRICT = "strict"
LANE_TREATMENT = "treatment"
LANES = (LANE_STRICT, LANE_TREATMENT)
LANE_ENV = "NEXUS_BENCH_LANE"
MAX_CALLS_ENV = "NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS"
DEFAULT_TREATMENT_MAX_MODEL_CALLS = 4
MAX_TREATMENT_MAX_MODEL_CALLS = 8
ARCHIVE_ENV = "NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR"
ROW_DEADLINE_ENV = "NEXUS_BENCH_ROW_DEADLINE_EPOCH"
TREATMENTS_ENABLED = ("self_heal", "multi_candidate", "ultra_review", "committee")
# Capability receipts that count as a treatment when classified ``real`` (attested).
RECEIPT_TREATMENTS = frozenset({
    "hyper",
    "sandbox",
    "ultra_review",
    "file_lock",
    "repair_loop",
    "committee",
    "autoreason",
    "ddtree",
})
# Product labels of a model-generated candidate (strict lane) plus the self-heal output.
MODEL_CANDIDATE_SOURCES = frozenset({"llm", "nexus_llm_baseline", "llm_assisted", "llm_self_heal"})
TREATMENT_WINNER_SOURCES = frozenset({"llm_self_heal"})
_TRUE = {"1", "true", "yes"}


def current_lane() -> str:
    return LANE_TREATMENT if os.environ.get(LANE_ENV, "").strip() == LANE_TREATMENT else LANE_STRICT


def lane_active() -> bool:
    return current_lane() == LANE_TREATMENT


def max_model_calls() -> int:
    try:
        return max(1, int(os.environ.get(MAX_CALLS_ENV) or DEFAULT_TREATMENT_MAX_MODEL_CALLS))
    except ValueError:
        return 1


def add_lane_arguments(parser: Any) -> None:
    parser.add_argument(
        "--lane",
        choices=list(LANES),
        default=LANE_STRICT,
        help=(
            "strict (default): one model call per with-Nexus row. treatment: same fairness rules, "
            "Nexus treatments on for the with-Nexus arm; rows carry first_attempt and after_treatment."
        ),
    )
    parser.add_argument(
        "--treatment-max-model-calls",
        dest="treatment_max_model_calls",
        type=int,
        default=None,
        help=f"Treatment lane: model calls allowed per with-Nexus row (default {DEFAULT_TREATMENT_MAX_MODEL_CALLS}).",
    )
    parser.add_argument(
        "--bare-retries",
        dest="bare_retries",
        type=int,
        default=0,
        help="Extra bare-arm attempts (recorded; only 0 is supported: the bare arm is the strict one).",
    )


def validate_lane_args(args: Any) -> list[str]:
    """Refusals; an empty list means the lane configuration keeps the strict lane's fairness."""

    lane = str(getattr(args, "lane", LANE_STRICT) or LANE_STRICT)
    errors: list[str] = []
    bare_retries = int(getattr(args, "bare_retries", 0) or 0)
    if bare_retries != 0:
        errors.append(
            "--bare-retries: only 0 is supported (the bare arm is the strict lane's one call)"
        )
    max_calls = getattr(args, "treatment_max_model_calls", None)
    if lane != LANE_TREATMENT:
        if max_calls is not None:
            errors.append("--treatment-max-model-calls needs --lane treatment")
        return errors
    if max_calls is not None and not 1 <= int(max_calls) <= MAX_TREATMENT_MAX_MODEL_CALLS:
        errors.append(f"--treatment-max-model-calls must be 1..{MAX_TREATMENT_MAX_MODEL_CALLS}")
    required = (
        ("strict_llm_baseline", "--strict-llm-baseline"),
        ("require_same_model_baseline", "--require-same-model-baseline"),
        ("counted_first_attempt", "--counted-first-attempt (not --allow-nexus-treatment)"),
        ("no_hidden_feedback", "--no-hidden-feedback"),
        ("no_nexus_task_hints", "--no-nexus-task-hints"),
        ("disable_promoted_route_cost_policy", "--disable-promoted-route-cost-policy"),
    )
    for attr, flag in required:
        if not bool(getattr(args, attr, False)):
            errors.append(f"--lane treatment needs {flag}")
    forbidden = (
        ("nexus_only", "--nexus-only"),
        ("without_only", "--without-only"),
        ("enable_background_offload", "--enable-background-offload"),
        ("skip_llm_baseline", "--skip-llm-baseline"),
    )
    for attr, flag in forbidden:
        if bool(getattr(args, attr, False)):
            errors.append(f"--lane treatment cannot be combined with {flag}")
    if str(getattr(args, "force_flow", "auto")) == "baseline":
        errors.append(
            "--lane treatment cannot be combined with --force-flow baseline (no treatment runs)"
        )
    if str(getattr(args, "without_mode", "")) != "agy":
        errors.append("--lane treatment needs --without-mode agy (same model and account leasing)")
    if str(getattr(args, "with_llm_mode", "off")) == "off":
        errors.append("--lane treatment needs a with-Nexus model mode (--with-llm-mode)")
    for name in ("NEXUS_ONLINE_LOCAL_ASSIST", "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED"):
        if os.environ.get(name, "").strip().lower() in _TRUE:
            errors.append(f"--lane treatment refuses {name}=1 (local/external paths stay off)")
    return errors


def configure_lane(args: Any) -> dict[str, Any]:
    """Set the lane for this process; returns the manifest fields. Call after validation."""

    lane = str(getattr(args, "lane", LANE_STRICT) or LANE_STRICT)
    os.environ[LANE_ENV] = lane
    manifest: dict[str, Any] = {
        "lane": lane,
        "bare_retries": int(getattr(args, "bare_retries", 0) or 0),
    }
    if lane != LANE_TREATMENT:
        os.environ.pop(MAX_CALLS_ENV, None)
        return manifest
    calls = int(
        getattr(args, "treatment_max_model_calls", None) or DEFAULT_TREATMENT_MAX_MODEL_CALLS
    )
    args.treatment_max_model_calls = calls
    os.environ[MAX_CALLS_ENV] = str(calls)
    # Hidden feedback stays impossible in the counted lanes, whatever else is set.
    os.environ["NEXUS_BENCH_NO_HIDDEN_FEEDBACK"] = "1"
    os.environ["NEXUS_BENCH_DISABLE_HIDDEN_RETRY"] = "1"
    os.environ["NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE"] = "1"
    if str(getattr(args, "force_flow", "auto")) == "auto":
        # The candidate pool and self-heal live in the hyper flow.
        args.force_flow = "hyper_sprint"
    manifest.update({
        "treatment_max_model_calls": calls,
        "treatments_enabled": list(TREATMENTS_ENABLED),
        "force_flow": args.force_flow,
    })
    return manifest


def model_winner_source_ok(winner: str) -> bool:
    """The treatment lane also delivers the visible-test self-heal output (a model candidate)."""

    return lane_active() and str(winner or "").strip().lower() in TREATMENT_WINNER_SOURCES


def new_candidate_archive() -> str:
    """A private per-row directory outside the workspace for the raw model candidates."""

    return tempfile.mkdtemp(prefix="nexus-bench-candidates-")


def with_nexus_env_overrides(*, deadline_epoch: float | None, archive_dir: str) -> dict[str, str]:
    """Env for the with-Nexus subprocess in the treatment lane ({} in the strict lane).

    Applied after the strict symmetric env: the symmetric prompt and every local-path disable stay
    as they are; only the treatment switches change.
    """

    if not lane_active():
        return {}
    calls = max_model_calls()
    env = {
        "NEXUS_BENCH_TREATMENT_LANE": "1",
        "NEXUS_SYMMETRIC_PROMPT": "1",
        "NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL": "1",
        "NEXUS_LLM_CANDIDATE_CAP": str(calls),
        MAX_CALLS_ENV: str(calls),
        "NEXUS_ULTRA_REVIEW_DRY_GATE": "1",
        "NEXUS_USE_COMMITTEE": "1",
        ARCHIVE_ENV: archive_dir,
        # unchanged fairness pins, re-asserted after the treatment switches
        "NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM": "1",
        "NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH": "1",
        "NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW": "1",
        "NEXUS_MODEL_REQUIRED_EXECUTION_MODE": "model_participation_only",
        "NEXUS_AUTO_NIGHTSHIFT_ON_HYPER_FAILURE": "0",
        "NEXUS_ONLINE_LOCAL_ASSIST": "0",
        "NEXUS_DISABLE_DAYSHIFT_OPTIMIZER": "1",
    }
    if deadline_epoch is not None:
        env[ROW_DEADLINE_ENV] = f"{float(deadline_epoch):.3f}"
    return env


def row_deadline_epoch(shared_task_deadline_monotonic: float | None) -> float | None:
    """The runner's monotonic row deadline as a wall-clock epoch for the product subprocess."""

    if shared_task_deadline_monotonic is None:
        return None
    return time.time() + (float(shared_task_deadline_monotonic) - time.monotonic())


def _report(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    report = result.get("report") if isinstance(result.get("report"), Mapping) else {}
    return report


def _trace(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    trace = _report(payload).get("learning_trace")
    return trace if isinstance(trace, Mapping) else {}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_archived_candidate(archive_dir: str, sha: str) -> str | None:
    if not archive_dir or len(sha) != 64:
        return None
    path = Path(archive_dir) / f"{sha}.txt"
    try:
        if path.is_symlink() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return text if _sha(text) == sha else None


# A verifier run on whatever is in the target file: the runner's own hidden or visible test
# command (same process group, staging and confinement as the strict lane), given a timeout.
RunTest = Callable[[int], subprocess.CompletedProcess[str]]


def _with_candidate(target_file: str, code: str, action: Callable[[], Any]) -> Any:
    """Run ``action`` with ``code`` in the target file; the delivered bytes are always put back."""

    target = Path(target_file)
    delivered = target.read_bytes() if target.exists() else None
    try:
        target.write_text(code, encoding="utf-8")
        return action()
    finally:
        if delivered is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(delivered)
        restored = target.read_bytes() if target.exists() else None
        if restored != delivered:
            raise RuntimeError("treatment lane could not restore the delivered target file")


def finalize_with_nexus_row(
    row: dict[str, Any],
    payload: Mapping[str, Any],
    *,
    target_file: str,
    verification_test_file: str,
    archive_dir: str,
    run_hidden: RunTest,
    run_visible: RunTest,
    timeout_sec: int,
    row_deadline_sec: float | None = None,
) -> dict[str, Any]:
    """Add the treatment-lane columns to a finished with-Nexus row (no-op in the strict lane)."""

    if not lane_active():
        return row
    trace = _trace(payload)
    shas = [
        str(item) for item in trace.get("model_candidate_sha256s") or [] if isinstance(item, str)
    ]
    sources = [str(item) for item in trace.get("model_candidate_sources") or []]
    first = shas[0] if shas else ""
    final = str(row.get("model_candidate_sha256") or "")
    final_index = max((i for i, sha in enumerate(shas) if sha == final), default=None)
    skipped = {
        "row_deadline": list(trace.get("treatment_rounds_skipped_row_deadline") or []),
        "call_budget": list(trace.get("treatment_rounds_skipped_call_budget") or []),
    }
    row.update({
        "lane": LANE_TREATMENT,
        "treatment_max_model_calls": max_model_calls(),
        "model_candidate_sha256s": shas,
        "model_candidate_sources": sources,
        "first_model_candidate_sha256": first,
        "final_model_candidate_sha256": final,
        "final_candidate_in_model_candidates": final_index is not None,
        "winner_candidate_index": final_index,
        "winner_round": None if final_index is None else final_index + 1,
        "treatment_rounds": len(shas),
        "treatment_rounds_skipped": skipped,
        "treatment_candidate_archive": archive_dir,
        "row_deadline_sec": row_deadline_sec,
        "tokens": int(row.get("total_tokens") or row.get("model_total_tokens") or 0),
        "treatment_applied": list(row.get("treatment_applied") or []),
    })
    _first_attempt(
        row,
        first=first,
        sources=sources,
        target_file=target_file,
        verification_test_file=verification_test_file,
        archive_dir=archive_dir,
        run_hidden=run_hidden,
        timeout_sec=timeout_sec,
    )
    row["treatment_visible_outputs"] = _visible_outputs(
        shas,
        target_file=target_file,
        archive_dir=archive_dir,
        run_visible=run_visible,
        timeout_sec=timeout_sec,
    )
    return row


def _first_attempt(
    row: dict[str, Any],
    *,
    first: str,
    sources: list[str],
    target_file: str,
    verification_test_file: str,
    archive_dir: str,
    run_hidden: RunTest,
    timeout_sec: int,
) -> None:
    """Score the first model candidate exactly like the strict lane: hidden test on its bytes."""

    row["first_attempt_hidden_passed"] = None
    if not first:
        row["first_attempt_status"] = "no_model_candidate"
        return
    if not sources or sources[0] not in MODEL_CANDIDATE_SOURCES:
        row["first_attempt_status"] = "first_candidate_not_model"
        return
    if Path(verification_test_file).name != "test_hidden.py":
        row["first_attempt_status"] = "no_hidden_verifier"
        return
    delivered = str(row.get("delivered_target_sha256") or "")
    if (
        first == delivered
        and row.get("hidden_verifier_file") == verification_test_file
        and isinstance(row.get("hidden_verifier_passed"), bool)
    ):
        # The first candidate is what was delivered: the row's own hidden verification scored it.
        row["first_attempt_hidden_passed"] = bool(row["hidden_verifier_passed"])
        row["first_attempt_status"] = "verified_as_delivered"
        return
    code = read_archived_candidate(archive_dir, first)
    if code is None:
        row["first_attempt_status"] = "first_candidate_unarchived"
        return

    def _verify() -> bool:
        return run_hidden(timeout_sec).returncode == 0

    try:
        row["first_attempt_hidden_passed"] = bool(_with_candidate(target_file, code, _verify))
        row["first_attempt_status"] = "verified_from_archive"
    except subprocess.TimeoutExpired:
        row["first_attempt_hidden_passed"] = False
        row["first_attempt_status"] = "hidden_verifier_timeout"


def _visible_outputs(
    shas: list[str],
    *,
    target_file: str,
    archive_dir: str,
    run_visible: RunTest,
    timeout_sec: int,
) -> dict[str, str]:
    """The runner's own visible-test output on every candidate that a later round could quote.

    The per-round prompt audit allows a ``[FAILURE]`` body only when its lines appear here.
    Only rows with more than one candidate need it; the visible test only, never the hidden one.
    """

    if len(shas) < 2:
        return {}
    out: dict[str, str] = {}
    for sha in dict.fromkeys(shas[:-1]):
        code = read_archived_candidate(archive_dir, sha)
        if code is None:
            continue

        def _visible() -> str:
            done = run_visible(timeout_sec)
            return f"{done.stdout or ''}\n{done.stderr or ''}"

        try:
            out[sha] = _with_candidate(target_file, code, _visible)[-20000:]
        except subprocess.TimeoutExpired:
            out[sha] = ""
    return out


def finalize_bare_row(row: dict[str, Any]) -> dict[str, Any]:
    """The bare arm in the treatment lane is the strict lane's bare arm (one call)."""

    if not lane_active():
        return row
    row["lane"] = LANE_TREATMENT
    row["bare_retries"] = 0
    row["tokens"] = int(row.get("total_tokens") or row.get("model_total_tokens") or 0)
    row.setdefault("treatment_applied", [])
    return row


def attest_row(row: dict[str, Any], task_audit: Mapping[str, Any] | None) -> None:
    """``treatment_applied`` from attested evidence only (receipts classified real, captures)."""

    if row.get("lane") != LANE_TREATMENT or str(row.get("mode")) != "with_nexus":
        return
    from scripts.bench.strict_llm_baseline import classify_receipt

    applied: set[str] = set()
    for receipt in row.get("capability_receipts") or []:
        if isinstance(receipt, dict) and str(receipt.get("name") or "") in RECEIPT_TREATMENTS:
            if classify_receipt(receipt) == "real":
                applied.add(str(receipt.get("name")))
    audit = task_audit or {}
    captured = int(audit.get("with_nexus_calls") or 0)
    sources = [str(item) for item in row.get("model_candidate_sources") or []]
    # The wrapper's call count must equal the row's; every recorded candidate came from one call.
    consistent = (
        captured > 0 and captured == int(row.get("model_calls") or 0) and len(sources) <= captured
    )
    if (
        consistent
        and int(audit.get("self_heal_rounds_observed") or 0) > 0
        and "llm_self_heal" in sources
    ):
        applied.add("self_heal")
    if consistent and sum(1 for item in sources if item != "llm_self_heal") >= 2:
        applied.add("multi_candidate")
    row["treatment_applied"] = sorted(applied)
    row["treatment_calls_reconciled"] = consistent
