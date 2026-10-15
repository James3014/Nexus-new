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

* ``first_attempt``: call 1's model candidate, scored exactly like the strict lane (the hidden
  test on those exact bytes, on a scratch copy of the task directory after the row ended);
* ``after_treatment``: the delivered (final) candidate.

The runner does not trust the product's account of its own rounds. The capture wrapper records
every with-Nexus prompt and model response; ``derive_runner_candidates`` re-derives each call's
candidate with the product's own extraction. The product's ``model_candidate_sha256s`` is
accepted only where it matches (its first entry must be call 1's candidate, every sha it names
must come from a captured response), otherwise the row is unverifiable and never a solve.

The bare arm is the strict lane's bare arm (one call): its ``after_treatment`` is its first attempt.
``--bare-retries`` exists so the choice is explicit and recorded; only 0 is supported.

The lane is refused until #2211's hidden-test staging and visible-test confinement are active
(``hidden_staging_ready``): without them a candidate could read ``test_hidden.py`` and carry
derived values into a later round.

``treatment_applied`` lists treatments with evidence: the runner-derived calls (self-heal,
several candidates) reconciled with the capture count, or capability receipts classified
``real`` (seam treatments also need the #2211 seam trigger and evidence ids). Receipts are
written by our own product subprocess (residual as in #2212 N3: consistency markers, not a
signature).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import stat
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
RESPONSE_DIR_ENV = "NEXUS_BENCH_RESPONSE_CAPTURE_DIR"
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
# Product labels of a stage-1 model candidate: the only possible first attempt.
STAGE1_MODEL_SOURCES = frozenset({"llm", "nexus_llm_baseline", "llm_assisted"})
# Stage-1 labels plus the self-heal output (a later model candidate).
MODEL_CANDIDATE_SOURCES = STAGE1_MODEL_SOURCES | {"llm_self_heal"}
ROUND_MIN_REMAINING_ENV = "NEXUS_BENCH_ROUND_MIN_REMAINING_SEC"
HIDDEN_STAGING_MODULE = "scripts.bench.hidden_test_staging"
# Lane-specific variables the strict lane must never inherit.
TREATMENT_ONLY_ENV = (
    "NEXUS_BENCH_TREATMENT_LANE",
    RESPONSE_DIR_ENV,
    "NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR",  # retired (round 2); never inherited
    ROW_DEADLINE_ENV,
    MAX_CALLS_ENV,
    ROUND_MIN_REMAINING_ENV,
)
NOT_RUN_TIMEOUT = "not_run:timeout"
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
    if os.environ.get(ROUND_MIN_REMAINING_ENV) is not None:
        errors.append(
            f"--lane treatment refuses a pre-set {ROUND_MIN_REMAINING_ENV} (the runner sets it)"
        )
    for attr, flag in (
        ("enable_ddtree_executor", "--enable-ddtree-executor"),
        ("enable_autoreason_executor", "--enable-autoreason-executor"),
        ("allow_learning_loop", "--allow-learning-loop"),
    ):
        # ddtree/autoreason keep the candidate loop going after a pass; the learning loop carries
        # state between trials.
        if bool(getattr(args, attr, False)):
            errors.append(f"--lane treatment cannot be combined with {flag}")
    ready, reason = hidden_staging_ready(args)
    if not ready:
        errors.append(f"treatment_requires_hidden_staging_and_confinement: {reason}")
    return errors


def hidden_staging_ready(args: Any) -> tuple[bool, str]:
    """The treatment lane needs #2211's hidden-test staging and visible-test confinement.

    Without them a later round could carry text a candidate derived from ``test_hidden.py``
    (the candidate runs next to it). Contract checked: the runner confines the visible test
    (``NEXUS_CONFINE_VISIBLE_TEST=1``), ``scripts.bench.hidden_test_staging`` is importable with
    ``staged_hidden_test`` / ``active_staging_for``, and the counted lane (which stages) is on.
    """

    if os.environ.get("NEXUS_CONFINE_VISIBLE_TEST", "") != "1":
        return False, "NEXUS_CONFINE_VISIBLE_TEST is not 1"
    try:
        module = importlib.import_module(HIDDEN_STAGING_MODULE)
    except ImportError:
        return False, f"{HIDDEN_STAGING_MODULE} is not available"
    for name in ("staged_hidden_test", "active_staging_for"):
        if not callable(getattr(module, name, None)):
            return False, f"{HIDDEN_STAGING_MODULE}.{name} missing"
    if not (
        bool(getattr(args, "strict_llm_baseline", False))
        and bool(getattr(args, "counted_first_attempt", False))
    ):
        return False, "hidden-test staging is active only in the counted strict configuration"
    return True, ""


def configure_lane(args: Any) -> dict[str, Any]:
    """Set the lane for this process; returns the manifest fields. Call after validation."""

    lane = str(getattr(args, "lane", LANE_STRICT) or LANE_STRICT)
    os.environ[LANE_ENV] = lane
    manifest: dict[str, Any] = {
        "lane": lane,
        "bare_retries": int(getattr(args, "bare_retries", 0) or 0),
    }
    if lane != LANE_TREATMENT:
        for name in TREATMENT_ONLY_ENV:
            os.environ.pop(name, None)  # the strict lane never inherits treatment switches
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


def response_capture_dir() -> str:
    """The run's private response-capture directory, next to the prompt-capture directory.

    The capture wrapper records each model response there (with-Nexus treatment rows only), so
    the runner derives every candidate from what the model actually returned. ``""`` when the
    run has no prompt capture (then every treatment row is unverifiable, never a solve).
    """

    capture = os.environ.get("NEXUS_BENCH_PROMPT_CAPTURE_DIR", "").strip()
    if not capture:
        return ""
    path = Path(f"{capture.rstrip('/')}.responses")
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        return ""
    return str(path)


def with_nexus_env_overrides(
    *, deadline_epoch: float | None, response_dir: str, per_call_cap_sec: int | None = None
) -> dict[str, str]:
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
        RESPONSE_DIR_ENV: response_dir,
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
    # A new round starts only with a full per-call cap left before the row deadline.
    env[ROUND_MIN_REMAINING_ENV] = str(int(per_call_cap_sec) if per_call_cap_sec else 300)
    return env


def row_deadline_epoch(shared_task_deadline_monotonic: float | None) -> float | None:
    """The runner's monotonic row deadline as a wall-clock epoch for the product subprocess."""

    if shared_task_deadline_monotonic is None:
        return None
    return time.time() + (float(shared_task_deadline_monotonic) - time.monotonic())


def _report(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    result = payload.get("result")
    if not isinstance(result, Mapping):
        return {}
    report = result.get("report")
    return report if isinstance(report, Mapping) else {}


def _trace(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    trace = _report(payload).get("learning_trace")
    return trace if isinstance(trace, Mapping) else {}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SELF_HEAL_SENTENCE = (
    "Previous candidate failed verification. Repair the candidate using the failure evidence below."
)
# Seam treatments (#2211) count only with the seam's own trigger and evidence on the receipt.
SEAM_TREATMENTS = frozenset({"sandbox", "ultra_review", "file_lock"})
SEAM_TRIGGER_PREFIX = "post_candidate_seam:"


def is_timeout_row(row: Mapping[str, Any]) -> bool:
    """The with-Nexus subprocess was killed (row deadline / subprocess timeout)."""

    return (
        row.get("treatment_timeout") is True
        or str(row.get("runtime_classification") or "") == "subprocess_timeout"
        or row.get("task_deadline_exceeded") is True
    )


def candidate_from_response(source_code: str, stdout: str) -> tuple[str, str]:
    """The candidate a captured agy response yields, with the product's own extraction.

    agy envelope -> ``response`` text -> ``_parse_operation_payload`` (edit JSON, else the whole
    text) -> ``_candidate_code_from_llm_output(source, out)``. ``("", reason)`` when none.
    """

    # The product's own transport parser (last JSON object on stdout, leading warnings tolerated).
    from nexus.research.sprint_service import (
        _OPERATION_EDIT_KEYS,
        _candidate_code_from_llm_output,
        _parse_operation_payload,
    )

    transport = importlib.import_module("nexus_runtime.kernel.transport")
    envelope = transport.parse_agy_envelope(stdout)
    text = str(envelope.get("response") or "") if isinstance(envelope, dict) else ""
    if not text.strip():
        return "", "no_model_response"
    parsed = _parse_operation_payload(text)
    out = (
        {key: parsed[key] for key in _OPERATION_EDIT_KEYS if key in parsed}
        if parsed
        else {"patch": text}
    )
    code, error = _candidate_code_from_llm_output(source_code, out)
    return (code or "", "" if code else (error or "no_candidate_code"))


def _private_entries(directory: Path, prefix: str) -> list[Path]:
    if not directory.is_dir() or directory.is_symlink():
        return []
    out = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith(prefix) and stat.S_ISREG(os.lstat(path).st_mode):
            out.append(path)
    return out


def derive_runner_candidates(*, original_source: str, key: str) -> tuple[list[dict[str, Any]], str]:
    """Every with-Nexus model call of this row, in call order, re-derived by the runner.

    Source of truth is the capture wrapper, not the product: the prompt record (call order,
    self-heal or stage 1) and the recorded model response. A stage-1 call edits the row's
    original source; a self-heal call edits the latest stage-1 candidate before it.
    """

    capture_dir = os.environ.get("NEXUS_BENCH_PROMPT_CAPTURE_DIR", "").strip()
    response_dir = os.environ.get(RESPONSE_DIR_ENV, "").strip()
    run_id = os.environ.get("NEXUS_BENCH_CAPTURE_RUN_ID", "").strip()
    if not capture_dir or not response_dir:
        return [], "no_response_capture"
    records: list[tuple[float, str, dict[str, Any]]] = []
    for path in _private_entries(Path(capture_dir), f"with_nexus__{key}__"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [], f"capture_unreadable:{path.name}"
        if (
            not isinstance(record, dict)
            or str(record.get("key")) != key
            or str(record.get("run_id")) != run_id
        ):
            continue
        records.append((float(record.get("ts") or 0.0), path.name, record))
    entries: list[dict[str, Any]] = []
    stage1_code: str | None = None
    for _ts, name, record in sorted(records):
        prompt = str(record.get("prompt") or "")
        self_heal = SELF_HEAL_SENTENCE in prompt
        entry: dict[str, Any] = {
            "kind": "self_heal" if self_heal else "stage1",
            "sha": "",
            "code": "",
            "error": "",
        }
        response_path = Path(response_dir) / name
        try:
            if not stat.S_ISREG(os.lstat(response_path).st_mode):
                raise OSError("not a regular file")
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entry["error"] = "no_response_recorded"
            entries.append(entry)
            continue
        if int(response.get("returncode") or 0) != 0:
            entry["error"] = "provider_failed"
        elif self_heal and stage1_code is None:
            entry["error"] = "self_heal_without_stage1_candidate"
        else:
            code, error = candidate_from_response(
                (stage1_code or "") if self_heal else original_source,
                str(response.get("stdout") or ""),
            )
            entry.update({"code": code, "sha": _sha(code) if code else "", "error": error})
            if code and not self_heal:
                stage1_code = code
        entries.append(entry)
    return entries, ""


# A test run on a scratch copy: (copied test file, scratch root used as cwd, timeout).
RunTest = Callable[[Path, Path, int], subprocess.CompletedProcess[str]]
HIDDEN_TEST_NAME = "test_hidden.py"


def _in_scratch_copy(
    target_file: str,
    test_file: str,
    code: str,
    action: Callable[[Path, Path], Any],
    *,
    exclude: frozenset[str] = frozenset(),
    pytest_ini: Path | None = None,
) -> Any:
    """Run ``action(copied_test, scratch_root)`` on a scratch copy of the task directory.

    The workspace is never written: a candidate that writes files only touches the copy. Files
    named in ``exclude`` (the hidden verifier for a visible re-run) are not copied. The repo's
    ``pytest.ini`` is copied to the scratch root, so the run has the strict scorer's pytest
    semantics (rootdir, addopts, import mode, asyncio mode, filters).
    """

    target = Path(target_file).resolve()
    test = Path(test_file).resolve()
    if target.parent != test.parent:
        raise RuntimeError("target_outside_test_directory")
    with tempfile.TemporaryDirectory(prefix="nexus-bench-rescore-") as tmp:
        root = Path(tmp)
        copy = root / test.parent.name
        shutil.copytree(
            test.parent,
            copy,
            symlinks=False,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", *sorted(exclude)),
        )
        if pytest_ini is not None and pytest_ini.is_file():
            shutil.copyfile(pytest_ini, root / "pytest.ini")
        (copy / target.name).write_text(code, encoding="utf-8")
        return action(copy / test.name, root)


def _repo_pytest_ini(repo_root: str | Path | None) -> Path | None:
    if not repo_root:
        return None
    ini = Path(repo_root) / "pytest.ini"
    return ini if ini.is_file() and not ini.is_symlink() else None


def finalize_with_nexus_row(
    row: dict[str, Any],
    payload: Mapping[str, Any],
    *,
    target_file: str,
    test_file: str,
    verification_test_file: str,
    original_source: str,
    key: str,
    run_hidden: RunTest,
    run_visible: RunTest,
    timeout_sec: int,
    row_deadline_sec: float | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Add the treatment-lane columns to a finished with-Nexus row (no-op in the strict lane).

    Every candidate is re-derived by the runner from the capture wrapper's records; the product's
    list is accepted only where it matches (first entry, and every sha it names).
    """

    if not lane_active():
        return row
    trace = _trace(payload)
    product_shas = [
        "" if item is None else str(item) for item in trace.get("model_candidate_sha256s") or []
    ]
    product_sources = [str(item) for item in trace.get("model_candidate_sources") or []]
    entries, capture_error = derive_runner_candidates(original_source=original_source, key=key)
    codes = {entry["sha"]: entry["code"] for entry in entries if entry["sha"]}
    runner_shas = [str(entry["sha"]) for entry in entries]
    unverified = sorted({sha for sha in product_shas if sha and sha not in codes})
    timeout = is_timeout_row(row) or is_timeout_row(payload)
    if timeout and int(row.get("model_calls") or 0) == 0 and entries:
        # The killed subprocess reported no calls; the wrapper saw them (H2).
        row["model_calls"] = len(entries)
        row["model_calls_source"] = "prompt_capture"
    runner_first = runner_shas[0] if runner_shas else ""
    product_first = product_shas[0] if product_shas else ""
    first_consistent = not product_shas or product_first == runner_first
    delivered = str(row.get("delivered_target_sha256") or "")
    final = str(row.get("model_candidate_sha256") or "")
    unverifiable = bool(capture_error) or bool(unverified) or not first_consistent
    final_bound = bool(final) and final == delivered and final in codes and not unverifiable
    final_index = (
        max((i for i, sha in enumerate(runner_shas) if sha == final), default=None)
        if final_bound
        else None
    )
    row.update({
        "lane": LANE_TREATMENT,
        "treatment_max_model_calls": max_model_calls(),
        "model_candidate_sha256s": product_shas,
        "model_candidate_sources": product_sources,
        "runner_candidate_sha256s": runner_shas,
        "runner_candidate_kinds": [entry["kind"] for entry in entries],
        "runner_candidate_errors": [entry["error"] for entry in entries],
        "treatment_unverified_shas": unverified,
        "treatment_unverifiable": unverifiable,
        "treatment_capture_error": capture_error,
        "first_model_candidate_sha256": runner_first,
        "final_model_candidate_sha256": final,
        "final_candidate_in_model_candidates": final_bound,
        "winner_candidate_index": final_index,
        "winner_round": None if final_index is None else final_index + 1,
        "treatment_rounds": len(entries),
        "treatment_rounds_skipped": {
            "row_deadline": list(trace.get("treatment_rounds_skipped_row_deadline") or []),
            "call_budget": list(trace.get("treatment_rounds_skipped_call_budget") or []),
        },
        "treatment_candidates": codes,
        "treatment_timeout": timeout,
        "row_deadline_sec": row_deadline_sec,
        "tokens": int(row.get("total_tokens") or row.get("model_total_tokens") or 0),
        "treatment_applied": list(row.get("treatment_applied") or []),
    })
    if timeout:
        # after_treatment of a killed row is a timeout (a failure that stays in the denominator,
        # S16); the first attempt is still scored from the runner-derived first candidate.
        row["after_treatment_status"] = NOT_RUN_TIMEOUT
    _first_attempt(
        row,
        entries=entries,
        capture_error=capture_error,
        first_consistent=first_consistent,
        target_file=target_file,
        verification_test_file=verification_test_file,
        run_hidden=run_hidden,
        timeout_sec=timeout_sec,
        pytest_ini=_repo_pytest_ini(repo_root),
    )
    row["treatment_visible_outputs"] = _visible_outputs(
        entries,
        target_file=target_file,
        test_file=test_file,
        run_visible=run_visible,
        timeout_sec=timeout_sec,
        exclude=frozenset({HIDDEN_TEST_NAME, Path(verification_test_file).name}),
        pytest_ini=_repo_pytest_ini(repo_root),
    )
    return row


def _first_attempt(
    row: dict[str, Any],
    *,
    entries: list[dict[str, Any]],
    capture_error: str,
    first_consistent: bool,
    target_file: str,
    verification_test_file: str,
    run_hidden: RunTest,
    timeout_sec: int,
    pytest_ini: Path | None = None,
) -> None:
    """Score the FIRST model call exactly like the strict lane: hidden test on its bytes.

    Only call 1's runner-derived stage-1 candidate can be a first attempt; a failed first call,
    a local fallback or a self-heal output never is.
    """

    row["first_attempt_hidden_passed"] = None
    if capture_error or not first_consistent:
        row["first_attempt_status"] = "first_attempt_unverifiable"
        return
    first = entries[0] if entries else None
    if first is None or not first["sha"]:
        row["first_attempt_status"] = "no_model_candidate"
        return
    if first["kind"] != "stage1":
        row["first_attempt_status"] = "first_candidate_not_model"
        return
    if Path(verification_test_file).name != "test_hidden.py":
        row["first_attempt_status"] = "no_hidden_verifier"
        return
    if (
        first["sha"] == str(row.get("delivered_target_sha256") or "")
        and row.get("hidden_verifier_file") == verification_test_file
        and isinstance(row.get("hidden_verifier_passed"), bool)
    ):
        # The runner-derived first candidate is the delivered file: the row's own hidden
        # verification scored exactly those bytes.
        row["first_attempt_hidden_passed"] = bool(row["hidden_verifier_passed"])
        row["first_attempt_status"] = "verified_as_delivered"
        return
    try:
        done = _in_scratch_copy(
            target_file,
            verification_test_file,
            first["code"],
            lambda test, root: run_hidden(test, root, timeout_sec),
            pytest_ini=pytest_ini,
        )
        row["first_attempt_hidden_passed"] = done.returncode == 0
        row["first_attempt_status"] = "verified_in_scratch_copy"
    except subprocess.TimeoutExpired:
        row["first_attempt_hidden_passed"] = False
        row["first_attempt_status"] = "hidden_verifier_timeout"
    except (OSError, RuntimeError, shutil.Error) as exc:
        row["first_attempt_status"] = "first_attempt_unverifiable"
        row["first_attempt_error"] = f"{type(exc).__name__}: {exc}"[:200]


def _visible_outputs(
    entries: list[dict[str, Any]],
    *,
    target_file: str,
    test_file: str,
    run_visible: RunTest,
    timeout_sec: int,
    exclude: frozenset[str] = frozenset({HIDDEN_TEST_NAME}),
    pytest_ini: Path | None = None,
) -> dict[str, str]:
    """The runner's own visible-test output on every stage-1 candidate a later round could quote.

    The per-round prompt audit allows a ``[FAILURE]`` body only when its lines appear here
    (after the hidden-literal scan of the whole prompt). Visible test only, on a scratch copy.
    """

    if len(entries) < 2:
        return {}
    out: dict[str, str] = {}
    for entry in entries[:-1]:
        if entry["kind"] != "stage1" or not entry["sha"] or entry["sha"] in out:
            continue

        def _visible(test: Path, root: Path) -> str:
            done = run_visible(test, root, timeout_sec)
            return f"{done.stdout or ''}\n{done.stderr or ''}"

        try:
            out[entry["sha"]] = _in_scratch_copy(
                target_file,
                test_file,
                entry["code"],
                _visible,
                exclude=exclude,
                pytest_ini=pytest_ini,
            )[-20000:]
        except (subprocess.TimeoutExpired, OSError, RuntimeError, shutil.Error):
            out[entry["sha"]] = ""
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


def _receipt_attested(receipt: Mapping[str, Any], stage1_calls: int) -> bool:
    """Receipt-based treatment evidence (residual, as in #2212 N3: the with-Nexus subprocess is
    our product and writes these receipts; overlay markers are consistency, not a signature).
    """

    from scripts.bench.strict_llm_baseline import classify_receipt

    name = str(receipt.get("name") or "")
    if name not in RECEIPT_TREATMENTS or classify_receipt(dict(receipt)) != "real":
        return False
    if name == "hyper" and stage1_calls <= 1:
        # One stage-1 candidate: the hyper pool did not run beyond the strict lane (a self-heal
        # round is counted as self_heal, not as hyper).
        return False
    if name in SEAM_TREATMENTS:
        # #2211 seam: its own trigger and sealed evidence ids, or it did not run post-candidate.
        trigger = str(receipt.get("trigger_source") or "")
        refs = [ref for ref in receipt.get("evidence_refs") or [] if str(ref).strip()]
        return trigger.startswith(SEAM_TRIGGER_PREFIX) and bool(refs)
    return True


def attest_row(row: dict[str, Any], task_audit: Mapping[str, Any] | None) -> None:
    """``treatment_applied`` from attested evidence only: receipts (see ``_receipt_attested``) and
    the runner-derived calls (self-heal / several candidates) reconciled with the capture count.
    """

    if row.get("lane") != LANE_TREATMENT or str(row.get("mode")) != "with_nexus":
        return
    audit = task_audit or {}
    captured = int(audit.get("with_nexus_calls") or 0)
    if is_timeout_row(row) and int(row.get("model_calls") or 0) == 0 and captured > 0:
        row["model_calls"] = captured
        row["model_calls_source"] = "prompt_capture"
    if audit.get("row_void"):
        # R2-3: a later round carried a hidden literal the model did not write itself: the row's
        # after_treatment is void (not a solve, stays in the denominator); round 1 stays scored.
        row["treatment_round_void"] = True
        row["after_treatment_status"] = "prompt_symmetry_violation"
        row["treatment_literal_hits"] = list(audit.get("treatment_literal_hits") or [])
    kinds = [str(kind) for kind in row.get("runner_candidate_kinds") or []]
    stage1_calls = sum(1 for kind in kinds if kind == "stage1")
    applied = {
        str(receipt.get("name"))
        for receipt in row.get("capability_receipts") or []
        if isinstance(receipt, Mapping) and _receipt_attested(receipt, stage1_calls)
    }
    shas = [str(sha) for sha in row.get("runner_candidate_sha256s") or []]
    consistent = (
        captured > 0
        and captured == int(row.get("model_calls") or 0) == len(kinds)
        and row.get("treatment_unverifiable") is not True
    )
    if (
        consistent
        and int(audit.get("self_heal_rounds_observed") or 0) > 0
        and any(kind == "self_heal" and sha for kind, sha in zip(kinds, shas))
    ):
        applied.add("self_heal")
    if consistent and sum(1 for kind, sha in zip(kinds, shas) if kind == "stage1" and sha) >= 2:
        applied.add("multi_candidate")
    row["treatment_applied"] = sorted(applied)
    row["treatment_calls_reconciled"] = consistent
