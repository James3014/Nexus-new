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
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
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
NOT_RUN_TIMEOUT = "not_run:timeout"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _treatment_env_template(
    *, calls: int, response_dir: str, deadline_epoch: float | None, per_call_cap_sec: int | None
) -> dict[str, str]:
    """THE treatment-lane env (one list: the strict lane clears exactly these keys, N6)."""

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
        # A new round starts only with a full per-call cap left before the row deadline.
        ROUND_MIN_REMAINING_ENV: str(int(per_call_cap_sec) if per_call_cap_sec else 300),
        ROW_DEADLINE_ENV: "" if deadline_epoch is None else f"{float(deadline_epoch):.3f}",
    }
    if deadline_epoch is None:
        env.pop(ROW_DEADLINE_ENV)
    return env


# Variables ONLY the treatment lane uses: the strict lane (the runner default) clears exactly
# these. Shared operator knobs in the template (self-heal, committee, ultra_review gate, local
# paths...) are NOT cleared: a non-counted run keeps the operator's setting, and the counted
# strict run pins each of them itself (``_strict_symmetric_with_nexus_env``) (R3-1).
TREATMENT_ONLY_ENV: tuple[str, ...] = (
    "NEXUS_BENCH_TREATMENT_LANE",
    RESPONSE_DIR_ENV,
    ROW_DEADLINE_ENV,
    MAX_CALLS_ENV,
    ROUND_MIN_REMAINING_ENV,
    "NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR",  # retired (round 2); never inherited
)
# Every key the treatment env sets: the treatment-only ones above plus shared knobs the counted
# strict env pins to its own values.
TREATMENT_ENV_KEYS: tuple[str, ...] = tuple(
    _treatment_env_template(calls=1, response_dir="", deadline_epoch=0.0, per_call_cap_sec=1)
)
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


# #2211 modules the treatment lane depends on, bound to THIS repository's files (N1): a stub
# module elsewhere on sys.path never satisfies the check.
BOUND_MODULES: dict[str, tuple[str, tuple[str, ...]]] = {
    HIDDEN_STAGING_MODULE: (
        "scripts/bench/hidden_test_staging.py",
        ("staged_hidden_test", "active_staging_for"),
    ),
    "nexus.engine.confined_test_runner": (
        "nexus/engine/confined_test_runner.py",
        ("run_confined_test", "run_pytest_dir_copy"),
    ),
    "nexus.services.post_candidate_seam": (
        "nexus/services/post_candidate_seam.py",
        ("run_visible_test_confined", "bench_forbidden_roots"),
    ),
}


def bound_module(name: str) -> Any:
    """Import ``name`` only if it is this repository's own file with the expected callables."""

    rel, callables = BOUND_MODULES[name]
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        raise RuntimeError(f"{name} is not available") from exc
    expected = (REPO_ROOT / rel).resolve()
    actual = Path(str(getattr(module, "__file__", "") or "")).resolve()
    if not expected.is_file() or actual != expected:
        raise RuntimeError(f"{name} is not the repository file ({actual})")
    for attr in callables:
        if not callable(getattr(module, attr, None)):
            raise RuntimeError(f"{name}.{attr} missing")
    return module


def hidden_staging_ready(args: Any) -> tuple[bool, str]:
    """The treatment lane needs #2211's hidden-test staging and confined runners.

    Without them a later round could carry text a candidate derived from ``test_hidden.py``.
    Contract checked: the runner confines the visible test (``NEXUS_CONFINE_VISIBLE_TEST=1``),
    the staging module, the confined test runner and the post-candidate seam are this
    repository's own files with their entry points, and the counted strict config (which stages)
    is on. The lane's own re-runs go through those confined runners only (``confined_*_runner``),
    so even a fooled gate never runs a candidate unconfined.
    """

    if os.environ.get("NEXUS_CONFINE_VISIBLE_TEST", "") != "1":
        return False, "NEXUS_CONFINE_VISIBLE_TEST is not 1"
    for name in BOUND_MODULES:
        try:
            bound_module(name)
        except RuntimeError as exc:
            return False, str(exc)
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
    return _treatment_env_template(
        calls=max_model_calls(),
        response_dir=response_dir,
        deadline_epoch=deadline_epoch,
        per_call_cap_sec=per_call_cap_sec,
    )


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


def _json_output_mode(argv: list[str]) -> bool:
    """agy ``--output-format json`` (the bench's runtime argv; the envelope is then REQUIRED by
    the pinned runtime, ``nexus_runtime/kernel/transport.py`` ``agy_envelope_missing``)."""

    for index, item in enumerate(argv):
        if item == "--output-format" and index + 1 < len(argv) and argv[index + 1] == "json":
            return True
        if item == "--output-format=json":
            return True
    return False


def derive_runner_candidates(
    *, original_source: str, key: str, row_start_epoch: float | None = None
) -> tuple[list[dict[str, Any]], str]:
    """Every with-Nexus model call of this row, in call order, re-derived by the runner.

    Source of truth is the capture wrapper, not the product: the prompt record (call order,
    self-heal or stage 1) and the recorded model response. A stage-1 call edits the row's
    original source; a self-heal call edits the latest stage-1 candidate before it.

    Order is the wrapper's per-row sequence number (``seq``), never a timestamp. Fail closed
    (N3) on a record from before the row started, on a sequence that is not exactly 0..n-1, and
    on a call made without agy's JSON output mode (the pinned runtime refuses those too).
    Residual (documented): the capture directories are writable by the same user as the
    product subprocess (our code); the model's code runs confined (#2211), which is the
    boundary for model-written code.
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
        if row_start_epoch is not None and float(record.get("ts") or 0.0) < float(row_start_epoch):
            return [], f"capture_record_before_row_start:{path.name}"
        try:
            seq = int(record["seq"])
        except (KeyError, TypeError, ValueError):
            return [], f"capture_sequence_missing:{path.name}"
        records.append((seq, path.name, record))
    records.sort(key=lambda item: item[0])
    if [seq for seq, _name, _record in records] != list(range(len(records))):
        return [], "capture_sequence_broken"
    entries: list[dict[str, Any]] = []
    stage1_code: str | None = None
    for _seq, name, record in records:
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
        argv = [str(item) for item in record.get("argv") or []]
        if int(response.get("returncode") or 0) != 0:
            entry["error"] = "provider_failed"
        elif not _json_output_mode(argv):
            entry["error"] = "agy_not_json_output_mode"
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


HIDDEN_TEST_NAME = "test_hidden.py"
RESCORE_KEY = "_treatment_rescore"
# run_hidden(code, target_file, hidden_test_file, timeout): the hidden verifier on ``code``.
RunHidden = Callable[[str, str, str, int], subprocess.CompletedProcess[str]]
# run_visible(code, original_code, target_file, visible_test_file, timeout): the visible test.
RunVisible = Callable[[str, str, str, str, int], subprocess.CompletedProcess[str]]


@contextmanager
def scratch_task_dir(target_file: str, test_file: str, code: str) -> Iterator[Path]:
    """A non-recursive copy of the test directory's regular files with ``code`` as the target.

    The same shape the strict scorer's hidden verifier copies (#2211 ``run_pytest_dir_copy``:
    regular files of the test directory, no dotfiles, no symlinks). Yields the copied test path.
    A target outside the test directory cannot be scored this way, by the strict scorer either
    (both datasets, P16 ``.nexus/bench_cases/<id>/`` and hard_v1 ``bench_fixtures/
    online_ab_hard_v1/<dir>/``, keep ``target.py`` next to the tests).
    """

    target = Path(target_file).resolve()
    test = Path(test_file).resolve()
    if target.parent != test.parent:
        raise RuntimeError("target_outside_test_directory")
    with tempfile.TemporaryDirectory(prefix="nexus-bench-rescore-") as tmp:
        root = Path(tmp)
        for entry in sorted(test.parent.iterdir()):
            if entry.name.startswith(".") or entry.is_symlink() or not entry.is_file():
                continue
            shutil.copyfile(entry, root / entry.name, follow_symlinks=False)
        (root / target.name).write_text(code, encoding="utf-8")
        yield root / test.name


def confined_hidden_runner(repo_root: str | Path) -> RunHidden:
    """The treatment lane's hidden re-score: the strict scorer's own confined runner (#2211).

    Never unconfined: without this repository's ``confined_test_runner`` / ``post_candidate_seam``
    it raises, and the row's first attempt is ``first_attempt_unverifiable``.
    """

    def run(
        code: str, target_file: str, hidden_test_file: str, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        runner = bound_module("nexus.engine.confined_test_runner")
        seam = bound_module("nexus.services.post_candidate_seam")
        with scratch_task_dir(target_file, hidden_test_file, code) as test:
            result = runner.run_pytest_dir_copy(
                test.parent,
                test.name,
                forbidden_paths=seam.bench_forbidden_roots(repo_root),
                timeout_sec=timeout,
            )
        argv = list(result.get("command") or [])
        if not result.get("executed"):
            raise RuntimeError(f"confinement_unavailable:{result.get('error')}")
        if result.get("timed_out"):
            raise subprocess.TimeoutExpired(argv, timeout)
        return subprocess.CompletedProcess(
            argv,
            int(result.get("exit_code") or 0),
            str(result.get("stdout_tail") or ""),
            str(result.get("stderr_tail") or ""),
        )

    return run


def confined_visible_runner(repo_root: str | Path) -> RunVisible:
    """The visible re-run: the product's own confined visible runner (#2211 seam), so the output
    the audit compares against comes from the same runner that produced the ``[FAILURE]`` text,
    with the hidden test excluded and forbidden."""

    def run(
        code: str, original: str, target_file: str, visible_test_file: str, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        bound_module("nexus.engine.confined_test_runner")  # the seam runs it; never a stub
        seam = bound_module("nexus.services.post_candidate_seam")
        completed, _executed = seam.run_visible_test_confined(
            target_path=target_file,
            visible_test_path=visible_test_file,
            original_code=original,
            candidate_code=code,
            timeout_sec=timeout,
            workspace_root=repo_root,
        )
        # Not executed: nothing ran; the refusal text is exactly what the product's own
        # confined visible run would have put into a failure tail (same function).
        return completed

    return run


def product_interpreter(argv0: str, repo_root: str | Path) -> str:
    """The product process's ``sys.executable``: its argv[0] made absolute against its cwd
    (``repo_root``), not resolved (CPython keeps the path it was started with). ``""`` for a
    launcher such as ``uv`` (unknown interpreter: no timeout line can be allowed)."""

    if not argv0 or os.sep not in argv0:
        return ""
    path = Path(argv0)
    return os.path.abspath(path if path.is_absolute() else Path(repo_root) / path)


def finalize_with_nexus_row(
    row: dict[str, Any],
    payload: Mapping[str, Any],
    *,
    target_file: str,
    test_file: str,
    verification_test_file: str,
    original_source: str,
    key: str,
    timeout_sec: int,
    row_deadline_sec: float | None = None,
    row_start_epoch: float | None = None,
    product_python: str = "",
    product_test_arg: str = "",
) -> dict[str, Any]:
    """Add the treatment-lane columns to a finished with-Nexus row (no-op in the strict lane).

    Every candidate is re-derived by the runner from the capture wrapper's records; the product's
    list is accepted only where it matches (first entry, and every sha it names). Nothing runs
    here: the first-attempt re-score and the visible re-runs happen in ``rescore_rows`` after all
    rows, outside any hidden-test staging window, through the confined runners only.
    """

    if not lane_active():
        return row
    trace = _trace(payload)
    product_shas = [
        "" if item is None else str(item) for item in trace.get("model_candidate_sha256s") or []
    ]
    product_sources = [str(item) for item in trace.get("model_candidate_sources") or []]
    entries, capture_error = derive_runner_candidates(
        original_source=original_source, key=key, row_start_epoch=row_start_epoch
    )
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
        "treatment_first_consistent": first_consistent,
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
        "first_attempt_hidden_passed": None,
        "first_attempt_status": "rescore_not_run",
        "treatment_visible_outputs": {},
        # The product's own interpreter and visible-test argument (the runner launched it): the
        # only interpreter / test a [FAILURE] timeout line may name (G5-1..G5-3).
        "treatment_product_python": product_python,
        "treatment_visible_test_arg": product_test_arg,
        RESCORE_KEY: {
            "target_file": str(target_file),
            "test_file": str(test_file),
            "verification_test_file": str(verification_test_file),
            "original_source": original_source,
            "timeout_sec": int(timeout_sec),
        },
    })
    if timeout:
        # after_treatment of a killed row is a timeout (a failure that stays in the denominator,
        # S16); the first attempt is still scored from the runner-derived first candidate.
        row["after_treatment_status"] = NOT_RUN_TIMEOUT
    return row


def _row_entries(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    codes = row.get("treatment_candidates") or {}
    return [
        {"kind": str(kind), "sha": str(sha), "code": str(codes.get(sha, "")) if sha else ""}
        for kind, sha in zip(
            row.get("runner_candidate_kinds") or [], row.get("runner_candidate_sha256s") or []
        )
    ]


def rescore_rows(
    rows: list[dict[str, Any]], *, run_hidden: RunHidden, run_visible: RunVisible
) -> None:
    """First-attempt re-score and visible re-runs for every finalized treatment row (end of run)."""

    for row in rows:
        job = row.pop(RESCORE_KEY, None)
        if not isinstance(job, Mapping):
            continue
        entries = _row_entries(row)
        _first_attempt(row, job=job, entries=entries, run_hidden=run_hidden)
        row["treatment_visible_outputs"] = _visible_outputs(
            entries, job=job, run_visible=run_visible
        )


def _first_attempt(
    row: dict[str, Any],
    *,
    job: Mapping[str, Any],
    entries: list[dict[str, Any]],
    run_hidden: RunHidden,
) -> None:
    """Score the FIRST model call exactly like the strict lane: hidden test on its bytes.

    Only call 1's runner-derived stage-1 candidate can be a first attempt; a failed first call,
    a local fallback or a self-heal output never is.
    """

    row["first_attempt_hidden_passed"] = None
    verification_test_file = str(job.get("verification_test_file") or "")
    if row.get("treatment_capture_error") or row.get("treatment_first_consistent") is False:
        row["first_attempt_status"] = "first_attempt_unverifiable"
        return
    first = entries[0] if entries else None
    if first is None or not first["sha"]:
        row["first_attempt_status"] = "no_model_candidate"
        return
    if first["kind"] != "stage1":
        row["first_attempt_status"] = "first_candidate_not_model"
        return
    if Path(verification_test_file).name != HIDDEN_TEST_NAME:
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
        done = run_hidden(
            first["code"],
            str(job.get("target_file") or ""),
            verification_test_file,
            int(job.get("timeout_sec") or 300),
        )
        row["first_attempt_hidden_passed"] = done.returncode == 0
        row["first_attempt_status"] = "verified_confined_rescore"
    except subprocess.TimeoutExpired:
        row["first_attempt_hidden_passed"] = False
        row["first_attempt_status"] = "hidden_verifier_timeout"
    except (OSError, RuntimeError, shutil.Error) as exc:
        row["first_attempt_status"] = "first_attempt_unverifiable"
        row["first_attempt_error"] = f"{type(exc).__name__}: {exc}"[:200]


def _visible_outputs(
    entries: list[dict[str, Any]], *, job: Mapping[str, Any], run_visible: RunVisible
) -> dict[str, str]:
    """The visible-test output on every stage-1 candidate a later round could quote.

    The per-round prompt audit allows a ``[FAILURE]`` body only when its lines appear here
    (after the hidden-literal scan of the whole prompt). Product's confined visible runner only.
    """

    if len(entries) < 2:
        return {}
    out: dict[str, str] = {}
    for entry in entries[:-1]:
        if entry["kind"] != "stage1" or not entry["sha"] or entry["sha"] in out:
            continue
        try:
            done = run_visible(
                entry["code"],
                str(job.get("original_source") or ""),
                str(job.get("target_file") or ""),
                str(job.get("test_file") or ""),
                int(job.get("timeout_sec") or 300),
            )
            out[entry["sha"]] = f"{done.stdout or ''}\n{done.stderr or ''}"[-20000:]
        except subprocess.TimeoutExpired as exc:
            # The same text the product's [FAILURE] tail carries for a hanging candidate (R5-1).
            out[entry["sha"]] = str(exc)
        except (OSError, RuntimeError, shutil.Error):
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
