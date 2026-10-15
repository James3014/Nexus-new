"""Wiring plan PR-3: the online A/B treatment lane (first attempt vs after treatment).

The treatment lane keeps every information-fairness rule of the strict lane (no hidden feedback,
no task hints, no local/deterministic solve, same model and per-call cap, one row deadline,
captured-prompt audit of EVERY call) and turns the product's treatments on for the with-Nexus
arm only. Rows carry ``first_attempt`` (call 1's model candidate scored exactly like the strict
lane) and ``after_treatment`` (the delivered candidate), plus model calls and tokens. Every
candidate is re-derived by the RUNNER from the capture wrapper's recorded model responses.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nexus.research import bench_treatment_lane as product_lane
from scripts.bench import treatment_lane as lane
from scripts.bench.agy_prompt_capture import capture_record, write_record, write_response
from scripts.bench.prompt_symmetry_audit import (
    NO_TOOLS_PREFIX,
    SELF_HEAL_SENTENCE,
    TaskMaterial,
    audit_run,
    load_block_schema,
    normalize_output_line,
)
from scripts.bench.strict_llm_baseline import (
    MODEL_SOLVE,
    NOT_SOLVED,
    TREATMENT_MODEL_SOLVE,
    apply_strict_llm_baseline_classification,
    apply_strict_llm_baseline_to_summary,
    honest_scorecard,
    lane_scorecard,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_environ():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def staging_ready(monkeypatch):
    """#2211's hidden-test staging + confinement (the lane refuses without them)."""

    monkeypatch.setattr(lane, "hidden_staging_ready", lambda _args: (True, ""))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- lane flag / refusals


def _fair_args(**overrides) -> argparse.Namespace:
    base = {
        "lane": "treatment",
        "treatment_max_model_calls": None,
        "bare_retries": 0,
        "strict_llm_baseline": True,
        "require_same_model_baseline": True,
        "counted_first_attempt": True,
        "no_hidden_feedback": True,
        "no_nexus_task_hints": True,
        "disable_promoted_route_cost_policy": True,
        "nexus_only": False,
        "without_only": False,
        "enable_background_offload": False,
        "skip_llm_baseline": False,
        "enable_ddtree_executor": False,
        "enable_autoreason_executor": False,
        "allow_learning_loop": False,
        "force_flow": "auto",
        "without_mode": "agy",
        "with_llm_mode": "all",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_strict_is_the_default_lane_and_needs_nothing() -> None:
    parser = argparse.ArgumentParser()
    lane.add_lane_arguments(parser)
    args = parser.parse_args([])
    assert (
        args.lane == "strict" and args.bare_retries == 0 and args.treatment_max_model_calls is None
    )
    assert lane.validate_lane_args(args) == []
    manifest = lane.configure_lane(args)
    assert manifest == {"lane": "strict", "bare_retries": 0}
    assert lane.current_lane() == "strict" and not lane.lane_active()
    assert lane.with_nexus_env_overrides(deadline_epoch=time.time() + 60, response_dir="/x") == {}


def test_treatment_lane_with_every_fairness_flag_is_accepted(staging_ready) -> None:
    args = _fair_args()
    assert lane.validate_lane_args(args) == []
    manifest = lane.configure_lane(args)
    assert manifest["lane"] == "treatment"
    assert manifest["treatment_max_model_calls"] == lane.DEFAULT_TREATMENT_MAX_MODEL_CALLS
    assert args.force_flow == "hyper_sprint"
    assert os.environ["NEXUS_BENCH_LANE"] == "treatment"
    # hidden feedback stays impossible whatever else is set
    assert os.environ["NEXUS_BENCH_NO_HIDDEN_FEEDBACK"] == "1"
    assert os.environ["NEXUS_BENCH_DISABLE_HIDDEN_RETRY"] == "1"
    assert os.environ["NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE"] == "1"


@pytest.mark.parametrize(
    "override, needle",
    [
        ({"strict_llm_baseline": False}, "--strict-llm-baseline"),
        ({"require_same_model_baseline": False}, "--require-same-model-baseline"),
        ({"counted_first_attempt": False}, "--counted-first-attempt"),
        ({"no_hidden_feedback": False}, "--no-hidden-feedback"),
        ({"no_nexus_task_hints": False}, "--no-nexus-task-hints"),
        ({"disable_promoted_route_cost_policy": False}, "--disable-promoted-route-cost-policy"),
        ({"nexus_only": True}, "--nexus-only"),
        ({"without_only": True}, "--without-only"),
        ({"enable_background_offload": True}, "--enable-background-offload"),
        ({"skip_llm_baseline": True}, "--skip-llm-baseline"),
        ({"enable_ddtree_executor": True}, "--enable-ddtree-executor"),
        ({"enable_autoreason_executor": True}, "--enable-autoreason-executor"),
        ({"allow_learning_loop": True}, "--allow-learning-loop"),
        ({"force_flow": "baseline"}, "--force-flow baseline"),
        ({"without_mode": "gemini"}, "--without-mode agy"),
        ({"with_llm_mode": "off"}, "--with-llm-mode"),
        ({"treatment_max_model_calls": 0}, "--treatment-max-model-calls"),
        ({"treatment_max_model_calls": 99}, "--treatment-max-model-calls"),
        ({"bare_retries": 2}, "--bare-retries"),
    ],
)
def test_treatment_lane_refuses_flags_that_break_fairness(staging_ready, override, needle) -> None:
    errors = lane.validate_lane_args(_fair_args(**override))
    assert errors and any(needle in error for error in errors), errors


def test_strict_lane_refuses_treatment_only_knobs() -> None:
    assert lane.validate_lane_args(_fair_args(lane="strict", treatment_max_model_calls=3))
    assert lane.validate_lane_args(_fair_args(lane="strict", bare_retries=1))


@pytest.mark.parametrize(
    "name",
    [
        "NEXUS_ONLINE_LOCAL_ASSIST",
        "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED",
        "NEXUS_BENCH_ROUND_MIN_REMAINING_SEC",
    ],
)
def test_treatment_lane_refuses_inherited_env(staging_ready, monkeypatch, name) -> None:
    monkeypatch.setenv(name, "1")
    assert any(name in error for error in lane.validate_lane_args(_fair_args()))


def test_treatment_lane_refused_until_hidden_staging_and_confinement(monkeypatch) -> None:
    """M2/N1: refused unless #2211's modules are THIS repository's files and confinement is on."""

    monkeypatch.delenv("NEXUS_CONFINE_VISIBLE_TEST", raising=False)
    errors = lane.validate_lane_args(_fair_args())
    assert any(e.startswith("treatment_requires_hidden_staging_and_confinement") for e in errors)
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    ready, reason = lane.hidden_staging_ready(_fair_args())
    real = all((REPO_ROOT / rel).is_file() for rel, _names in lane.BOUND_MODULES.values())
    assert ready is real, reason
    if real:
        assert lane.hidden_staging_ready(_fair_args(counted_first_attempt=False))[0] is False


def test_a_stub_staging_module_does_not_satisfy_the_gate(monkeypatch, tmp_path: Path) -> None:
    """N1 probe: a module with the right name and dummy callables, but not the repo's file."""

    import types

    for name in lane.BOUND_MODULES:
        stub = types.ModuleType(name)
        stub.__file__ = str(tmp_path / "stub.py")
        for attr in lane.BOUND_MODULES[name][1]:
            setattr(stub, attr, lambda *_a, **_k: None)
        monkeypatch.setitem(sys.modules, name, stub)
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    ready, reason = lane.hidden_staging_ready(_fair_args())
    assert ready is False and "not the repository file" in reason
    with pytest.raises(RuntimeError):
        lane.bound_module("nexus.engine.confined_test_runner")


def test_lane_rescore_never_runs_unconfined_without_the_repo_runners(
    monkeypatch, tmp_path: Path
) -> None:
    """N1: the lane's own re-score / visible re-run go through the confined runners only; with a
    stub (or missing) runner they refuse, and the row is unverifiable, never scored unconfined."""

    import types

    stub = types.ModuleType("nexus.engine.confined_test_runner")
    stub.__file__ = str(tmp_path / "stub.py")
    stub.run_confined_test = stub.run_pytest_dir_copy = lambda *_a, **_k: {
        "executed": True,
        "exit_code": 0,
    }
    monkeypatch.setitem(sys.modules, "nexus.engine.confined_test_runner", stub)
    case = tmp_path / "case"
    case.mkdir()
    (case / "target.py").write_text("x = 0\n", encoding="utf-8")
    (case / "test_hidden.py").write_text("def test_x():\n    assert False\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        lane.confined_hidden_runner(tmp_path)(
            "x = 1\n", str(case / "target.py"), str(case / "test_hidden.py"), 10
        )
    with pytest.raises(RuntimeError):
        lane.confined_visible_runner(tmp_path)(
            "x = 1\n", "x = 0\n", str(case / "target.py"), str(case / "test_v.py"), 10
        )


def test_strict_lane_clears_inherited_treatment_switches(monkeypatch) -> None:
    """M3/N6/R3-1: the strict lane (the runner default) clears ONLY the treatment-only keys;
    shared operator knobs stay as the operator set them."""

    monkeypatch.setenv("NEXUS_BENCH_LANE", "treatment")
    every = set(
        lane.with_nexus_env_overrides(deadline_epoch=1.0, response_dir="/r", per_call_cap_sec=5)
    )
    assert every == set(lane.TREATMENT_ENV_KEYS)
    assert set(lane.TREATMENT_ONLY_ENV) - {"NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR"} <= every
    shared = every - set(lane.TREATMENT_ONLY_ENV)
    assert {
        "NEXUS_USE_COMMITTEE",
        "NEXUS_ULTRA_REVIEW_DRY_GATE",
        "NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL",
    } <= shared
    for name in [*lane.TREATMENT_ONLY_ENV, *shared]:
        monkeypatch.setenv(name, "1")
    lane.configure_lane(_fair_args(lane="strict"))
    for name in lane.TREATMENT_ONLY_ENV:
        assert name not in os.environ, name
    for name in shared:
        assert os.environ.get(name) == "1", name


def test_default_non_counted_run_keeps_the_operators_self_heal(monkeypatch, tmp_path: Path) -> None:
    """R3-1 probe: a plain runner invocation with NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 keeps it."""

    import scripts.bench.capability_ab_runner as runner

    class _Stop(Exception):
        pass

    seen: dict[str, str] = {}

    def stop(_args, **_kwargs):
        seen["self_heal"] = os.environ.get("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "")
        seen["committee"] = os.environ.get("NEXUS_USE_COMMITTEE", "")
        raise _Stop

    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(runner, "build_public_benchmark_preflight", stop)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/public_benchmark_nexus_value_v1.json",
            "--output-dir",
            str(tmp_path / "out"),
            "--preflight-only",
        ],
    )
    with pytest.raises(_Stop):
        runner.main()
    assert seen == {"self_heal": "1", "committee": "1"}


def test_counted_strict_run_pins_committee_and_ultra_review_off(
    tmp_path: Path, monkeypatch
) -> None:
    """R3-1: inherited committee / ultra_review dry-gate = 1 never reach a counted strict row."""

    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DRY_GATE", "1")
    _row, envs = _with_nexus_row(
        tmp_path, monkeypatch, lane_name="strict", candidates=[GOOD_CLASSIFY]
    )
    assert envs[0]["NEXUS_USE_COMMITTEE"] == "0"
    assert envs[0]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "0"
    assert envs[0]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "0"


def test_bound_module_needs_the_repo_file_to_exist(monkeypatch, tmp_path: Path) -> None:
    """LOW: a stub whose __file__ is spoofed to the (absent) repository path does not pass."""

    import types

    name = "scripts.bench.hidden_test_staging"
    expected = lane.REPO_ROOT / lane.BOUND_MODULES[name][0]
    stub = types.ModuleType(name)
    stub.__file__ = str(expected)
    stub.staged_hidden_test = stub.active_staging_for = lambda *_a, **_k: None
    monkeypatch.setitem(sys.modules, name, stub)
    if expected.is_file():
        assert lane.bound_module(name) is stub  # the real file: the binding is by path
    else:
        with pytest.raises(RuntimeError):
            lane.bound_module(name)


def _cli(monkeypatch, tmp_path: Path, *flags: str) -> dict[str, str]:
    import scripts.bench.capability_ab_runner as runner

    class _Stop(Exception):
        pass

    seen: dict[str, str] = {}

    def stop(args, **_kwargs):
        seen["lane"] = os.environ.get("NEXUS_BENCH_LANE", "")
        seen["force_flow"] = str(args.force_flow)
        seen["no_hidden_feedback"] = os.environ.get("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", "")
        raise _Stop

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_AGY_COMMAND", raising=False)
    monkeypatch.setattr(runner, "build_public_benchmark_preflight", stop)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/public_benchmark_nexus_value_v1.json",
            "--output-dir",
            str(tmp_path / "out"),
            "--preflight-only",
            *flags,
        ],
    )
    with pytest.raises(_Stop):
        runner.main()
    return seen


FAIR_CLI = (
    "--strict-llm-baseline",
    "--require-same-model-baseline",
    "--without-mode",
    "agy",
    "--with-llm-mode",
    "all",
    "--with-model-provider",
    "gemini",
    "--per-call-timeout-sec",
    "300",
    "--timeout-sec",
    "420",
)


def test_cli_lane_treatment_reaches_the_run_with_the_lane_set(
    staging_ready, monkeypatch, tmp_path: Path
) -> None:
    seen = _cli(monkeypatch, tmp_path, *FAIR_CLI, "--lane", "treatment")
    assert seen == {"lane": "treatment", "force_flow": "hyper_sprint", "no_hidden_feedback": "1"}
    default = _cli(monkeypatch, tmp_path, *FAIR_CLI)
    assert default["lane"] == "strict" and default["force_flow"] == "auto"


def test_cli_refuses_the_treatment_lane_without_hidden_staging(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(lane, "hidden_staging_ready", lambda _args: (False, "missing"))
    with pytest.raises(SystemExit) as exc:
        _cli(monkeypatch, tmp_path, *FAIR_CLI, "--lane", "treatment")
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "flags",
    [
        ("--lane", "treatment"),  # no strict baseline at all
        (*FAIR_CLI, "--lane", "treatment", "--allow-nexus-treatment"),
        (*FAIR_CLI, "--lane", "treatment", "--nexus-only"),
        (*FAIR_CLI, "--lane", "treatment", "--force-flow", "baseline"),
        (*FAIR_CLI, "--lane", "treatment", "--enable-ddtree-executor"),
        (*FAIR_CLI, "--lane", "treatment", "--allow-learning-loop"),
        (*FAIR_CLI, "--bare-retries", "1"),
        (*FAIR_CLI, "--treatment-max-model-calls", "3"),
    ],
)
def test_cli_refuses_unfair_lane_combinations(
    staging_ready, monkeypatch, tmp_path: Path, flags
) -> None:
    with pytest.raises(SystemExit) as exc:
        _cli(monkeypatch, tmp_path, *flags)
    assert exc.value.code == 2


def test_treatment_env_turns_treatments_on_and_keeps_the_fairness_pins(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BENCH_LANE", "treatment")
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "3")
    deadline = time.time() + 120
    env = lane.with_nexus_env_overrides(
        deadline_epoch=deadline, response_dir="/tmp/r", per_call_cap_sec=240
    )
    assert env["NEXUS_BENCH_TREATMENT_LANE"] == "1"
    assert env["NEXUS_SYMMETRIC_PROMPT"] == "1"  # same prompt contract as the strict lane
    assert env["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"
    assert (
        env["NEXUS_LLM_CANDIDATE_CAP"] == "3"
        and env["NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS"] == "3"
    )
    assert env["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1" and env["NEXUS_USE_COMMITTEE"] == "1"
    for pinned, value in {
        "NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM": "1",
        "NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH": "1",
        "NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW": "1",
        "NEXUS_MODEL_REQUIRED_EXECUTION_MODE": "model_participation_only",
        "NEXUS_AUTO_NIGHTSHIFT_ON_HYPER_FAILURE": "0",
        "NEXUS_ONLINE_LOCAL_ASSIST": "0",
        "NEXUS_DISABLE_DAYSHIFT_OPTIMIZER": "1",
    }.items():
        assert env[pinned] == value, pinned
    assert abs(float(env["NEXUS_BENCH_ROW_DEADLINE_EPOCH"]) - deadline) < 1.0
    assert env["NEXUS_BENCH_RESPONSE_CAPTURE_DIR"] == "/tmp/r"
    # a new round needs a full per-call cap left (H2)
    assert env["NEXUS_BENCH_ROUND_MIN_REMAINING_SEC"] == "240"
    assert "NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR" not in env


def test_row_deadline_epoch_tracks_the_monotonic_row_deadline() -> None:
    assert lane.row_deadline_epoch(None) is None
    epoch = lane.row_deadline_epoch(time.monotonic() + 100)
    assert abs(epoch - (time.time() + 100)) < 1.0


# --------------------------------------------------------------------------- product hooks


def test_product_lane_flag_needs_the_symmetric_prompt(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_LANE", "1")
    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    assert product_lane.treatment_lane_active() is False
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    assert product_lane.treatment_lane_active() is True


def test_record_model_candidate_keeps_call_order_with_failed_call_placeholders() -> None:
    trace: dict = {}
    product_lane.record_failed_model_call(trace)
    second = product_lane.record_model_candidate(trace, "a = 2\n", "llm")
    assert trace["model_candidate_sha256s"] == [None, second]
    assert trace["model_candidate_sources"] == ["llm_failed", "llm"]
    assert trace["first_model_candidate_sha256"] is None


def test_one_row_deadline_and_call_budget_cover_every_round(monkeypatch) -> None:
    trace: dict = {}
    for name in (
        "NEXUS_BENCH_ROW_DEADLINE_EPOCH",
        "NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS",
        "NEXUS_BENCH_ROUND_MIN_REMAINING_SEC",
        "NEXUS_GATEWAY_TIMEOUT_SEC",
    ):
        monkeypatch.delenv(name, raising=False)
    assert product_lane.treatment_round_allowed(trace, "self_heal", 3) is True
    now = time.time()
    # without an explicit minimum a round needs the per-call cap (gateway timeout) left
    monkeypatch.setenv("NEXUS_GATEWAY_TIMEOUT_SEC", "300")
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(now + 200))
    assert product_lane.row_deadline_allows_round(trace, "self_heal", now=now) is False
    assert trace["treatment_rounds_skipped_row_deadline"] == ["self_heal"]
    monkeypatch.setenv("NEXUS_BENCH_ROUND_MIN_REMAINING_SEC", "120")
    assert product_lane.row_deadline_allows_round(trace, "candidate_1", now=now) is True
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", "not-a-number")
    assert product_lane.row_deadline_allows_round(trace, "x") is False
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(time.time() + 600))
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "2")
    assert product_lane.treatment_round_allowed(trace, "self_heal", 1) is True
    assert product_lane.treatment_round_allowed(trace, "candidate_2", 2) is False
    assert trace["treatment_rounds_skipped_call_budget"] == ["candidate_2"]


class _GenFail(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.metadata = {"model_calls": 1, "tokens_used": 11}


def _sprint(monkeypatch, tmp_path: Path, *, treatment: bool, answers: list):
    """run_hyper_sprint with a fake generator; each answer is code or an Exception to raise."""

    from nexus.research import sprint_service
    from nexus.research.sprint_service import CandidateEval, SprintConfig, run_hyper_sprint

    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    phase_slo.parent.mkdir(parents=True, exist_ok=True)
    phase_slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8"
    )
    (tmp_path / "demo.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )
    calls: list[dict] = []

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **kwargs):
            calls.append(dict(kwargs))
            answer = answers[min(len(calls), len(answers)) - 1]
            if isinstance(answer, Exception):
                raise answer
            return answer, {"source": "llm", "model_calls": 1, "tokens_used": 7}

    class FakeLocal:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, **kwargs):
            return "def value():\n    return 9\n", {"source": "local"}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            ok = "return 2" in kwargs["code"]
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0 if ok else 0.4,
                stdout="" if ok else "E       assert 3 == 2\n1 failed in 0.01s",
                candidate_code=kwargs["code"],
                source=kwargs["source"],
            )

    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    if treatment:
        monkeypatch.setenv("NEXUS_BENCH_TREATMENT_LANE", "1")
    else:
        monkeypatch.delenv("NEXUS_BENCH_TREATMENT_LANE", raising=False)
    monkeypatch.setattr(sprint_service, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(sprint_service, "SprintExecutor", FakeExecutor)
    if hasattr(sprint_service, "LocalSprintMutator"):
        monkeypatch.setattr(sprint_service, "LocalSprintMutator", FakeLocal)
    monkeypatch.setattr(
        "nexus.research.flow.codeintel_context.sprint_codeintel_block", lambda *_a, **_k: ""
    )
    cfg = SprintConfig(
        task="fix value",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    return run_hyper_sprint(repo_root=tmp_path, config=cfg), calls


BAD_VALUE = "def value():\n    return 3\n"
GOOD_VALUE = "def value():\n    return 2\n"


def test_sprint_treatment_lane_self_heals_and_records_every_model_candidate(
    monkeypatch, tmp_path: Path
) -> None:
    res, calls = _sprint(monkeypatch, tmp_path, treatment=True, answers=[BAD_VALUE, GOOD_VALUE])
    trace = res.learning_trace
    assert len(calls) == 2
    assert trace["model_candidate_sha256s"] == [_sha(BAD_VALUE), _sha(GOOD_VALUE)]
    assert trace["model_candidate_sources"] == ["llm", "llm_self_heal"]
    assert trace["first_model_candidate_sha256"] == _sha(BAD_VALUE)
    repair_task = calls[1]["task"]
    assert SELF_HEAL_SENTENCE in repair_task and "[FAILURE]" in repair_task
    # The local support candidate never reaches the audited prompt.
    assert "[NEXUS LOCAL SUPPORT CANDIDATE]" not in repair_task
    assert res.winner_source == "llm_self_heal" and res.patch == GOOD_VALUE


def test_sprint_failed_first_call_is_a_placeholder_and_a_local_fallback_is_never_repaired(
    monkeypatch, tmp_path: Path
) -> None:
    """H1 (reviewer probe): call 1 fails (no patch), the sprint falls back to a local candidate.

    The local candidate must never be sent to self-heal, and the first entry is the failed call,
    so the row can never become a first-attempt solve.
    """

    res, calls = _sprint(
        monkeypatch, tmp_path, treatment=True, answers=[RuntimeError("llm_no_patch"), GOOD_VALUE]
    )
    trace = res.learning_trace
    assert len(calls) == 1, "no self-heal of a local fallback candidate"
    assert trace["model_candidate_sha256s"][0] is None
    assert trace["model_candidate_sources"][0] == "llm_failed"
    assert "llm_self_heal" not in trace["model_candidate_sources"]


def test_sprint_failed_self_heal_call_is_still_counted(monkeypatch, tmp_path: Path) -> None:
    """G5: a repair call that raises still counts (call budget, calls and tokens)."""

    res, calls = _sprint(
        monkeypatch, tmp_path, treatment=True, answers=[BAD_VALUE, _GenFail("gateway timeout")]
    )
    assert len(calls) == 2
    assert res.model_calls == 2
    assert res.total_tokens >= 7 + 11
    assert res.learning_trace["model_candidate_sources"] == ["llm", "llm_self_heal_failed"]


def test_sprint_strict_lane_stays_at_one_model_call(monkeypatch, tmp_path: Path) -> None:
    res, calls = _sprint(monkeypatch, tmp_path, treatment=False, answers=[BAD_VALUE, GOOD_VALUE])
    assert len(calls) == 1
    assert res.learning_trace["model_candidate_sha256s"] == [_sha(BAD_VALUE)]


def test_sprint_treatment_round_skipped_near_the_row_deadline(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(time.time() + 5))
    res, calls = _sprint(monkeypatch, tmp_path, treatment=True, answers=[BAD_VALUE, GOOD_VALUE])
    assert len(calls) == 1
    assert res.learning_trace["treatment_rounds_skipped_row_deadline"] == ["self_heal"]


def test_sprint_treatment_round_skipped_at_the_call_budget(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "1")
    res, calls = _sprint(monkeypatch, tmp_path, treatment=True, answers=[BAD_VALUE, GOOD_VALUE])
    assert len(calls) == 1
    assert res.learning_trace["treatment_rounds_skipped_call_budget"] == ["self_heal"]


# --------------------------------------------------------------------------- per-round prompt audit

VISIBLE = "def test_v():\n    assert classify(False, {'verified': True}) == 'open'\n"
HIDDEN = (
    "def test_h():\n"
    "    assert classify(True, {'verified': True}) == 'resolved'\n"
    "    assert classify(True, {'verified': False}) == 'needs_evidence'\n"
)
SOURCE = "def classify(smoke_passed, semantic_evidence):\n    return 'open'\n"
# Round-1 model candidate: fails the visible test; contains no hidden-only literal.
CANDIDATE1 = "def classify(smoke_passed, semantic_evidence):\n    return 'closed'\n"
FINAL = "def classify(smoke_passed, semantic_evidence):\n    return 'open' if not smoke_passed else 'closed'\n"
KEY = "nexus-value-trust-002__1"
TASK_LINE = "Task: Fix an incident classifier."
BARE = (
    NO_TOOLS_PREFIX
    + f"\n\n{TASK_LINE}\n\n[CURRENT SOURCE]\n"
    + SOURCE
    + "\n[CURRENT TESTS]\n"
    + VISIBLE
)
NEXUS_HEAD = (
    "You are an agent wearing Nexus. Use the Nexus route, CodeIntel, governance, and artifact "
    "constraints below. Stay within the task scope.\n\n" + NO_TOOLS_PREFIX + "\n\n"
    '[NEXUS ROUTE SUMMARY]\n{"recommended_flow":"hyper","risk_score":55}\n\n'
    '[NEXUS EXECUTION PROFILE]\n{"candidate_count":4}\n\n'
    "[NEXUS HIDDEN-VERIFIER GUIDANCE]\n\n"
)
ROUND1 = NEXUS_HEAD + "\n[TASK]\n" + BARE.replace(NO_TOOLS_PREFIX, "")
VISIBLE_OUTPUT = (
    "F                                                                        [100%]\n"
    "=================================== FAILURES ===================================\n"
    "____________________________________ test_v ____________________________________\n"
    "test_visible.py:2: AssertionError\n"
    "E       AssertionError: assert 'closed' == 'open'\n"
    "1 failed in 0.03s\n"
)
PY = "/opt/homebrew/opt/python@3.14/bin/python3.14"  # an '@' in the path (G5-2)
VISIBLE_ARG = ".nexus/bench_cases/nexus-value-trust-002/test_visible.py"
TIMEOUT_LINE = (
    f"Command '['{PY}', '-m', 'pytest', '-q', '--maxfail=1', '--', "
    f"'{VISIBLE_ARG}']' timed out after 60 seconds"
)


def _round2(failure: str = "", *, candidate: str = CANDIDATE1, extra: str = "") -> str:
    tail = failure or (
        "_ test_v _\n"
        "test_visible.py:2: AssertionError\n"
        "E       AssertionError: assert 'closed' == 'open'\n"
        "1 failed in 0.05s\n"
    )
    return (
        NEXUS_HEAD
        + "\n[TASK]\n"
        + f"{TASK_LINE}\n\n{SELF_HEAL_SENTENCE}\n[FAILURE]\n{tail}\n"
        + extra
        + "\n[CURRENT SOURCE]\n"
        + candidate
        + "\n[CURRENT TESTS]\n"
        + VISIBLE
    )


def _capture(tmp_path: Path, arm: str, prompt: str) -> None:
    write_record(
        capture_record(
            ["--model", "m", "--print", prompt],
            "",
            {
                "NEXUS_BENCH_ARM": arm,
                "NEXUS_BENCH_CAPTURE_KEY": KEY,
                "NEXUS_BENCH_CAPTURE_RUN_ID": "r1",
            },
        ),
        str(tmp_path),
    )
    time.sleep(0.002)  # captures are ordered by timestamp


def _rows(
    *, model_calls: int = 2, max_calls: int = 4, candidates: dict | None = None
) -> list[dict]:
    texts = (
        candidates if candidates is not None else {_sha(CANDIDATE1): CANDIDATE1, _sha(FINAL): FINAL}
    )
    return [
        {
            "mode": "without_nexus",
            "task_id": "nexus-value-trust-002",
            "trial_index": 1,
            "model_calls": 1,
        },
        {
            "mode": "with_nexus",
            "task_id": "nexus-value-trust-002",
            "trial_index": 1,
            "model_calls": model_calls,
            "attempt_count": 3,
            "lane": "treatment",
            "treatment_max_model_calls": max_calls,
            "treatment_candidates": texts,
            "runner_candidate_sha256s": list(texts),
            "treatment_product_python": PY,
            "treatment_visible_test_arg": VISIBLE_ARG,
            "treatment_visible_outputs": {_sha(CANDIDATE1): VISIBLE_OUTPUT},
        },
    ]


def _material() -> dict[str, TaskMaterial]:
    return {
        KEY: TaskMaterial(
            task_id="nexus-value-trust-002",
            visible_test=VISIBLE,
            hidden_test=HIDDEN,
            source=SOURCE,
        )
    }


def _audit(
    tmp_path: Path, round2: str | None, *, lane_name: str = "treatment", rows=None, **row_kwargs
) -> dict:
    captures = tmp_path / "captures"
    captures.mkdir(parents=True)
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", ROUND1)
    if round2 is not None:
        _capture(captures, "with_nexus", round2)
    return audit_run(
        captures, _material(), rows=rows or _rows(**row_kwargs), run_id="r1", lane=lane_name
    )


def test_treatment_round_two_self_heal_prompt_passes(tmp_path: Path) -> None:
    report = _audit(tmp_path, _round2())
    assert report["status"] == "PASS", json.dumps(report, indent=1)
    task = report["tasks"][0]
    assert task["with_nexus_calls"] == 2 and task["treatment_rounds_audited"] == 1
    assert task["self_heal_rounds_observed"] == 1


def test_strict_lane_still_fails_a_second_with_nexus_call(tmp_path: Path) -> None:
    report = _audit(tmp_path, _round2(), lane_name="strict")
    assert report["status"] == "FAIL"
    assert "with_nexus_calls=2" in report["tasks"][0]["violations"]


def test_round_one_of_the_treatment_lane_gets_every_strict_check(tmp_path: Path) -> None:
    """Round 1 is audited like the strict lane; only the four widened config numbers differ."""

    report = _audit(tmp_path, None, model_calls=1)
    assert report["status"] == "PASS", json.dumps(report, indent=1)
    strict = _audit(tmp_path / "s", None, model_calls=1, lane_name="strict")
    assert "nexus_block_string_not_allowed" in strict["tasks"][0]["violations"]  # hyper / 4


def test_schema_widening_touches_only_the_listed_paths() -> None:
    """Treatment-lane schema = strict schema plus: the 4 listed config numbers, any sprint attempt
    id (s<n>-a<k>) where the strict schema pins s0-a1, and semantic_failure_sensor cloned from
    file_lock's patterns (the planner adds it after a failed visible test). Nothing else."""

    strict = load_block_schema("strict")
    treatment = load_block_schema("treatment")
    listed = {
        ("[NEXUS EXECUTOR FLAGS]", "ddtree_max_candidates"),
        ("[NEXUS ROUTE SUMMARY]", "recommended_flow"),
        ("[NEXUS EXECUTION PROFILE]", "candidate_count"),
        ("[NEXUS EXECUTION PROFILE]", "max_rounds"),
    }
    changed = set()
    for header, paths in strict.items():
        for path, spec in paths.items():
            new = treatment[header][path]
            if new == spec:
                continue
            changed.add((header, path))
            if (header, path) in listed:
                continue
            assert set(new) == set(spec) and new["kind"] == spec["kind"]
            for pattern in new["patterns"]:
                original = pattern.replace("semantic_failure_sensor", "file_lock").replace(
                    "\\-s[0-9]{1,5}\\-a[0-9]{1,2}", "\\-s0\\-a1"
                )
                assert original in spec["patterns"], pattern
    assert listed <= changed
    assert ("[NEXUS CAPABILITY EVIDENCE]", "task_id") in changed
    assert ("[NEXUS ROUTE SUMMARY]", "selected_capabilities[]") in changed


@pytest.mark.parametrize(
    "round2, violation",
    [
        # a hidden-only literal that is not the model's own text
        (
            _round2(extra="Note: unverified evidence maps to needs_evidence.\n"),
            "treatment_round_not_allowed",
        ),
        # a hidden test line
        (
            _round2(extra="    assert classify(True, {'verified': False}) == 'needs_evidence'\n"),
            "hidden_test_line_in_with_nexus_prompt",
        ),
        # task hints the bare arm never sees (capitalised and lowercase, M1 / G1 probes)
        (
            _round2(extra="Hint: return open unless the evidence is verified.\n"),
            "treatment_round_not_allowed",
        ),
        (
            _round2(extra="hint: return open unless the evidence is verified.\n"),
            "treatment_round_not_allowed",
        ),
        (
            _round2(
                extra="note: please use binary search on variable nums to find target answer 42.\n"
            ),
            "treatment_round_not_allowed",
        ),
        # a timeout line whose argv is not the product's visible-test command (M1 probe)
        (
            _round2(extra="Command '[return open unless verified]' timed out after 1 seconds\n"),
            "treatment_round_not_allowed",
        ),
        # failure text the runner's own visible run never printed
        (
            _round2(failure="E   expected the canonical closed status\n"),
            "treatment_round_not_allowed",
        ),
        # the local support candidate block
        (
            _round2(extra="[NEXUS LOCAL SUPPORT CANDIDATE]\nreturn 'resolved'\n"),
            "treatment_round_not_allowed",
        ),
        # a "candidate" that is not one of the row's runner-derived model candidates
        (
            _round2(
                candidate="def classify(smoke_passed, semantic_evidence):\n    return smoke_passed and 'x'\n"
            ),
            "treatment_round_not_allowed",
        ),
    ],
    ids=[
        "hidden_literal",
        "hidden_line",
        "hint",
        "hint_lowercase",
        "note_lowercase",
        "free_text_timeout",
        "failure_not_in_visible_output",
        "local_support",
        "non_model_candidate",
    ],
)
def test_treatment_round_two_fails_closed(tmp_path: Path, round2: str, violation: str) -> None:
    report = _audit(tmp_path, round2)
    assert report["status"] == "FAIL"
    assert violation in report["tasks"][0]["violations"], report["tasks"][0]


def test_product_error_codes_and_the_exact_timeout_line_pass(tmp_path: Path) -> None:
    report = _audit(tmp_path, _round2(failure=f"no_change_candidate\n{TIMEOUT_LINE}\n"))
    assert report["status"] == "PASS", report["tasks"][0]
    hidden = TIMEOUT_LINE.replace("test_visible.py", "test_hidden.py")
    assert _audit(tmp_path / "h", _round2(failure=hidden + "\n"))["status"] == "FAIL"


def test_model_candidate_and_visible_output_never_exempt_a_hidden_literal(tmp_path: Path) -> None:
    """G2 + R2-3: a literal is exempt ONLY inside a line byte-identical to an EARLIER runner-derived
    candidate line. A failure tail quoting it is not exempt: the row is voided (not a solve, the
    run is not aborted). Round 1 and hidden test LINES keep the hard abort."""

    leaky = "def classify(smoke_passed, semantic_evidence):\n    x = 'needs_evidence'\n    return 'closed'\n"
    rows = _rows(candidates={_sha(leaky): leaky, _sha(FINAL): FINAL})
    rows[1]["treatment_visible_outputs"] = {
        _sha(leaky): VISIBLE_OUTPUT + "E AssertionError: assert 'needs_evidence' == 'open'\n"
    }
    quoted = _audit(tmp_path, _round2(candidate=leaky), rows=rows)
    task = quoted["tasks"][0]
    assert quoted["status"] == "PASS", task
    assert task["treatment_literal_hits"] == [] and task["row_void"] is False
    tail = _audit(
        tmp_path / "t",
        _round2(candidate=leaky, failure="E AssertionError: assert 'needs_evidence' == 'open'\n"),
        rows=rows,
    )
    task = tail["tasks"][0]
    assert tail["status"] == "PASS", task  # not a run abort ...
    assert (
        task["row_void"] is True and "needs_evidence" in task["treatment_literal_hits"]
    )  # ... a void row
    # the candidate line must be byte-identical: a re-indented copy is not the model's line
    moved = _audit(tmp_path / "m", _round2(candidate=leaky.replace("    x =", "  x =")), rows=rows)
    assert moved["tasks"][0]["row_void"] is True


def test_round_one_literal_and_later_hidden_line_still_abort(tmp_path: Path) -> None:
    rows = _rows(model_calls=1)
    round1 = ROUND1.replace(TASK_LINE, TASK_LINE + " needs_evidence")
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", round1)
    first = audit_run(captures, _material(), rows=rows, run_id="r1", lane="treatment")
    assert "hidden_literal_in_with_nexus_prompt" in first["tasks"][0]["violations"]
    line = _audit(
        tmp_path / "l",
        _round2(extra="    assert classify(True, {'verified': False}) == 'needs_evidence'\n"),
    )
    assert line["status"] == "FAIL"
    assert "hidden_test_line_in_with_nexus_prompt" in line["tasks"][0]["violations"]


def test_void_row_is_not_a_solve_and_stays_in_the_denominator() -> None:
    row = _treated_row()
    lane.attest_row(row, {"with_nexus_calls": 2, "row_void": True, "treatment_literal_hits": ["x"]})
    assert row["after_treatment_status"] == "prompt_symmetry_violation"
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == NOT_SOLVED and row["after_treatment"] is False
    assert lane_scorecard([row], "with_nexus")["total_n"] == 1


def test_captured_calls_must_equal_row_model_calls_and_the_cap(tmp_path: Path) -> None:
    mismatch = _audit(tmp_path, _round2(), model_calls=3)
    assert any(
        v.startswith("with_nexus_calls_mismatch") for v in mismatch["tasks"][0]["violations"]
    )
    over = _audit(tmp_path / "o", _round2(), max_calls=1)
    assert "with_nexus_calls=2>treatment_max=1" in over["tasks"][0]["violations"]


def test_killed_row_with_zero_reported_calls_is_not_a_mismatch(tmp_path: Path) -> None:
    """H2: a subprocess-timeout payload reports 0 calls; the captured calls are its calls."""

    rows = _rows(model_calls=0)
    rows[1]["runtime_classification"] = "subprocess_timeout"
    report = _audit(tmp_path, _round2(), rows=rows)
    assert not any(
        v.startswith("with_nexus_calls_mismatch") for v in report["tasks"][0]["violations"]
    )
    rows[1]["lane"] = "treatment"
    lane.attest_row(rows[1], report["tasks"][0])
    assert rows[1]["model_calls"] == 2 and rows[1]["model_calls_source"] == "prompt_capture"


def test_bare_arm_stays_at_one_call_in_the_treatment_lane(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "without_nexus", BARE + "\nretry\n")
    _capture(captures, "with_nexus", ROUND1)
    report = audit_run(
        captures, _material(), rows=_rows(model_calls=1), run_id="r1", lane="treatment"
    )
    assert "bare_calls=2" in report["tasks"][0]["violations"]


def test_tampered_candidate_text_fails_the_round_audit(tmp_path: Path) -> None:
    rows = _rows()
    rows[1]["treatment_candidates"] = {_sha(CANDIDATE1): CANDIDATE1 + "# edited\n"}
    report = _audit(tmp_path, _round2(), rows=rows)
    assert report["status"] == "FAIL"
    assert any(
        "candidate_sha_mismatch" in f for f in report["tasks"][0]["treatment_round_findings"]
    )


def test_runner_rescue_is_a_row_violation_in_the_treatment_lane(tmp_path: Path) -> None:
    rows = _rows(model_calls=1)
    rows[1]["bounded_nexus_rescue_used"] = True
    report = _audit(tmp_path, None, rows=rows)
    assert any("runner_rescue_in_treatment_lane" in v for v in report["row_violations"])


def test_output_line_normalisation_drops_only_volatile_parts() -> None:
    # directories are kept: a path can never smuggle text past the visible-output match (G5-3)
    assert (
        normalize_output_line("/tmp/a/b/test_visible.py:2: AssertionError")
        == "/tmp/a/b/test_visible.py:2: AssertionError"
    )
    assert normalize_output_line("==== 1 failed in 0.03s ====") == "1 failed in Xs"
    assert normalize_output_line("E   assert 'x' == 'y'") == "E assert 'x' == 'y'"


def test_failed_audit_voids_both_columns_and_marks_the_run_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    """A per-round FAIL makes every row of the run a prompt_symmetry_violation (runner exit 3)."""

    from scripts.bench.capability_ab_runner import _apply_prompt_symmetry_audit

    monkeypatch.setenv("NEXUS_BENCH_LANE", "treatment")
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", ROUND1)
    _capture(captures, "with_nexus", _round2(extra="hint: closed when unverified.\n"))
    rows = _rows()
    for row in rows:
        row.update({"status": "SUCCESS", "hidden_verifier_passed": True})
    rows[1].update({
        "first_attempt_hidden_passed": True,
        "first_attempt_status": "verified_confined_rescore",
        "first_model_candidate_sha256": _sha(CANDIDATE1),
    })
    report = _apply_prompt_symmetry_audit(
        (captures, "r1"), _material(), rows, out_dir=tmp_path / "out"
    )
    assert report["status"] == "FAIL" and report["lane"] == "treatment"
    apply_strict_llm_baseline_classification(rows)
    for row in rows:
        assert row["run_eligible"] is False and row["prompt_symmetry_violation"] is True
        assert row["first_attempt"] is False and row["after_treatment"] is False


# --------------------------------------------------------------------------- columns and scorecard


def _treated_row(**overrides) -> dict:
    a, b = _sha("a"), _sha("b")
    row = {
        "mode": "with_nexus",
        "task_id": "t",
        "trial_index": 1,
        "lane": "treatment",
        "status": "SUCCESS",
        "model_calls": 2,
        "total_tokens": 300,
        "nexus_winner_source": "llm_self_heal",
        "model_candidate_sha256": b,
        "model_candidate_sha256s": [a, b],
        "model_candidate_sources": ["llm", "llm_self_heal"],
        "runner_candidate_sha256s": [a, b],
        "runner_candidate_kinds": ["stage1", "self_heal"],
        "treatment_unverifiable": False,
        "first_model_candidate_sha256": a,
        "final_model_candidate_sha256": b,
        "final_candidate_in_model_candidates": True,
        "first_attempt_hidden_passed": False,
        "first_attempt_status": "verified_confined_rescore",
        "treatment_applied": ["self_heal"],
    }
    row.update(overrides)
    return row


def test_after_treatment_solve_is_not_a_first_attempt_solve() -> None:
    row = _treated_row()
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == TREATMENT_MODEL_SOLVE
    assert row["first_attempt"] is False and row["after_treatment"] is True
    assert row["tokens"] == 300


def test_first_candidate_delivered_counts_in_both_columns() -> None:
    a = _sha("a")
    row = _treated_row(
        model_calls=1,
        nexus_winner_source="llm",
        model_candidate_sha256=a,
        final_model_candidate_sha256=a,
        model_candidate_sha256s=[a],
        model_candidate_sources=["llm"],
        runner_candidate_sha256s=[a],
        runner_candidate_kinds=["stage1"],
        first_attempt_hidden_passed=True,
        first_attempt_status="verified_as_delivered",
    )
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == MODEL_SOLVE
    assert row["first_attempt"] is True and row["after_treatment"] is True


def test_self_heal_after_a_failed_first_call_is_never_a_first_attempt_solve() -> None:
    """H1: call 1 produced nothing; a delivered self-heal/second candidate is treatment only."""

    b = _sha("b")
    row = _treated_row(
        model_candidate_sha256s=[None, b],
        model_candidate_sources=["llm_failed", "llm_self_heal"],
        runner_candidate_sha256s=["", b],
        runner_candidate_kinds=["stage1", "self_heal"],
        first_model_candidate_sha256="",
        first_attempt_hidden_passed=None,
        first_attempt_status="no_model_candidate",
    )
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == TREATMENT_MODEL_SOLVE
    assert row["first_attempt"] is False


def test_delivered_candidate_outside_the_runner_candidates_never_counts() -> None:
    row = _treated_row(
        final_candidate_in_model_candidates=False,
        model_candidate_sha256=_sha("local"),
        final_model_candidate_sha256=_sha("local"),
    )
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == NOT_SOLVED and row["treatment_sha_unbound"] is True
    assert row["after_treatment"] is False


def test_unverifiable_row_never_counts_after_treatment() -> None:
    row = _treated_row(treatment_unverifiable=True)
    apply_strict_llm_baseline_classification([row])
    assert row["after_treatment"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"nexus_winner_source": "local_hidden_shadow"},
        {"hidden_retry_used": True},
        {"model_calls": 0},
    ],
    ids=["local_winner", "hidden_feedback", "no_model_call"],
)
def test_local_and_hidden_feedback_deliveries_are_never_counted(overrides) -> None:
    row = _treated_row(first_attempt_hidden_passed=True, **overrides)
    apply_strict_llm_baseline_classification([row])
    assert row["after_treatment"] is False
    if "hidden_retry_used" in overrides or "model_calls" in overrides:
        assert row["first_attempt"] is False


def test_lane_scorecard_reports_both_columns_gain_and_cost() -> None:
    bare = {
        "mode": "without_nexus",
        "task_id": "t",
        "trial_index": 1,
        "status": "FAILED",
        "model_calls": 1,
        "total_tokens": 100,
        "lane": "treatment",
    }
    bare2 = {**bare, "task_id": "u", "status": "SUCCESS"}
    a = _sha("a")
    solved_first = _treated_row(
        task_id="u",
        model_calls=1,
        total_tokens=120,
        nexus_winner_source="llm",
        model_candidate_sha256=a,
        final_model_candidate_sha256=a,
        model_candidate_sha256s=[a],
        model_candidate_sources=["llm"],
        runner_candidate_sha256s=[a],
        runner_candidate_kinds=["stage1"],
        first_attempt_hidden_passed=True,
        first_attempt_status="verified_as_delivered",
        treatment_applied=[],
    )
    rows = [bare, bare2, _treated_row(), solved_first]
    apply_strict_llm_baseline_classification(rows)
    summary = {"with_nexus": {}, "without_nexus": {}}
    apply_strict_llm_baseline_to_summary(rows, summary)
    card = summary["with_nexus"]["lane_scorecard"]
    assert (
        card["first_attempt"] == 1 and card["after_treatment"] == 2 and card["treatment_gain"] == 1
    )
    assert card["model_calls_total"] == 3 and card["extra_model_calls"] == 1
    assert card["tokens_total"] == 420 and card["tokens_per_extra_solve"] == 420.0
    assert card["treatment_applied"] == {"self_heal": 1}
    bare_card = lane_scorecard(rows, "without_nexus")
    assert bare_card["first_attempt"] == bare_card["after_treatment"] == 1
    scorecard = summary["with_nexus"]["scorecard"]
    assert scorecard["solved_by_model"] == 1 and scorecard["solved_by_model_after_treatment"] == 1
    assert scorecard["failed"] == 0


def test_strict_lane_rows_have_equal_columns() -> None:
    row = {
        "mode": "with_nexus",
        "status": "SUCCESS",
        "model_calls": 1,
        "nexus_winner_source": "llm",
        "total_tokens": 9,
    }
    apply_strict_llm_baseline_classification([row])
    assert row["first_attempt"] is True and row["after_treatment"] is True and row["tokens"] == 9


# Strict-lane output on main (3d39a2479) for these two rows; the PR only ADDS keys (G7).
MAIN_STRICT_WITH = {
    "mode": "with_nexus",
    "status": "SUCCESS",
    "model_calls": 1,
    "nexus_winner_source": "llm",
    "total_tokens": 9,
    "task_id": "t",
    "trial_index": 1,
    "strict_llm_baseline_applied": True,
    "rescued_by_local": False,
    "deterministic_rescue": False,
    "solve_classification": "model_solve",
    "capabilities_real": [],
    "capabilities_real_unattested": [],
    "capabilities_simulated": [],
    "capabilities_selected_not_invoked": [],
    "capabilities_real_self_reported": [],
    "capabilities_blocked_missing_inputs": [],
    "capability_blocked_reasons": {},
    "capabilities_failed_or_refused": [],
    "capability_failed_reasons": {},
    "capabilities_not_executable": [],
    "capability_not_exercised": True,
    "solve_without_capability": True,
}
MAIN_STRICT_BARE = {
    "mode": "without_nexus",
    "status": "FAILED",
    "model_calls": 1,
    "total_tokens": 3,
    "task_id": "t",
    "trial_index": 1,
    "strict_llm_baseline_applied": True,
    "rescued_by_local": False,
    "solve_classification": "not_solved",
    "deterministic_rescue": False,
}
ADDITIVE_ROW_KEYS = {"first_attempt", "after_treatment", "tokens", "treatment_applied"}
MAIN_SCORECARD_KEYS = {
    "contract_violation",
    "contract_violation_failed",
    "failed",
    "infra_invalid",
    "model_solve_rate_all_rows",
    "rescued_by_local",
    "schema",
    "solved_by_model",
    "total_n",
    "wiring_defects",
}


def test_strict_lane_output_differs_from_main_only_by_additive_keys() -> None:
    keys = (
        "mode",
        "status",
        "model_calls",
        "nexus_winner_source",
        "total_tokens",
        "task_id",
        "trial_index",
    )
    rows = [
        {k: MAIN_STRICT_WITH[k] for k in keys},
        {k: MAIN_STRICT_BARE[k] for k in keys if k in MAIN_STRICT_BARE},
    ]
    apply_strict_llm_baseline_classification(rows)
    for row, main in zip(rows, (MAIN_STRICT_WITH, MAIN_STRICT_BARE)):
        assert set(row) - set(main) == ADDITIVE_ROW_KEYS
        assert {k: row[k] for k in main} == main
    card = honest_scorecard(copy.deepcopy(rows), "with_nexus")
    assert set(card) - MAIN_SCORECARD_KEYS == {"solved_by_model_after_treatment"}
    assert MAIN_SCORECARD_KEYS <= set(card)


def test_treatment_applied_comes_from_attested_evidence_only() -> None:
    attested = {
        "attestation": "real",
        "attestation_source": "unified_capability_projection",
        "attestation_refs_resolved": True,
        "attestation_disposition": {"kind": "succeeded"},
        "selected": True,
        "invoked": True,
        "evidence_refs": ["ref1"],
        "claim_boundary": {"simulated": False},
    }
    row = _treated_row(
        treatment_rounds=1,
        capability_receipts=[
            {
                "name": "ultra_review",
                "selected": True,
                "invoked": True,
                "attestation": "real_self_reported",
                "evidence_refs": ["x"],
            },
            {**attested, "name": "sandbox"},  # no seam trigger: not counted (G6)
            {**attested, "name": "ultra_review", "trigger_source": "post_candidate_seam:verify"},
            {**attested, "name": "hyper"},  # one round: not counted (L1)
        ],
        treatment_applied=["claimed_by_product"],
    )
    lane.attest_row(row, {"with_nexus_calls": 2, "self_heal_rounds_observed": 1})
    assert row["treatment_applied"] == ["self_heal", "ultra_review"]
    assert row["treatment_calls_reconciled"] is True
    unreconciled = _treated_row()
    lane.attest_row(unreconciled, {"with_nexus_calls": 1, "self_heal_rounds_observed": 1})
    assert unreconciled["treatment_applied"] == []
    unverified = _treated_row(treatment_unverifiable=True)
    lane.attest_row(unverified, {"with_nexus_calls": 2, "self_heal_rounds_observed": 1})
    assert unverified["treatment_applied"] == []


# --------------------------------------------------------------------------- zero-model end to end

GOOD_CLASSIFY = (
    "def classify(smoke_passed, semantic_evidence):\n"
    "    if not smoke_passed:\n"
    "        return 'open'\n"
    "    if isinstance(semantic_evidence, dict) and semantic_evidence.get('verified') is True:\n"
    "        return 'resolved'\n"
    "    return 'needs_evidence'\n"
)
BAD_CLASSIFY = "def classify(smoke_passed, semantic_evidence):\n    return 'resolved'\n"


def _agy_stdout(code: str) -> str:
    return json.dumps({
        "conversation_id": "c",
        "status": "SUCCESS",
        "response": json.dumps({"patch": code}),
    })


def _with_nexus_row(
    tmp_path: Path,
    monkeypatch,
    *,
    lane_name: str,
    candidates: list,
    product_list=None,
    timeout: bool = False,
) -> tuple[dict, list[dict]]:
    """run_with_nexus with a fake product subprocess (zero model calls) and the REAL hidden test.

    The fake also plays the capture wrapper: one prompt record + recorded response per call. A
    ``None`` candidate is a call that returned no usable answer.
    """

    from scripts.bench.capability_ab_runner import (
        _materialize_fixture,
        load_tasks,
        run_with_nexus,
    )
    from scripts.bench.capability_ab_runner import (
        _run_process_group as real_run_process_group,
    )

    capture = tmp_path / "captures"
    capture.mkdir(mode=0o700, parents=True)
    monkeypatch.setenv("NEXUS_BENCH_PROMPT_CAPTURE_DIR", str(capture))
    monkeypatch.setenv("NEXUS_BENCH_CAPTURE_RUN_ID", "run1")
    monkeypatch.setenv("NEXUS_BENCH_ARM", "with_nexus")
    monkeypatch.setenv("NEXUS_BENCH_CAPTURE_KEY", "nexus-value-trust-002__1")
    monkeypatch.setenv("NEXUS_BENCH_NO_TASK_HINTS", "1")
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.setenv("NEXUS_BENCH_LANE", lane_name)
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "4")
    # what main() sets for both counted lanes (no bounded hyper rescue, no hidden retry)
    monkeypatch.setenv("NEXUS_BENCH_COUNTED_FIRST_ATTEMPT", "1")
    monkeypatch.setenv("NEXUS_BENCH_NO_HIDDEN_FEEDBACK", "1")
    monkeypatch.setenv("NEXUS_BENCH_DISABLE_HIDDEN_RETRY", "1")
    monkeypatch.setenv("NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE", "1")
    tasks = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")
    task = next(t for t in tasks if t.id == "nexus-value-trust-002")
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    envs: list[dict] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            envs.append(dict(env))
            treatment = env.get("NEXUS_BENCH_TREATMENT_LANE") == "1"
            produced = candidates if treatment else candidates[:1]
            response_dir = env.get("NEXUS_BENCH_RESPONSE_CAPTURE_DIR", "")
            trace: dict = {}
            for index, code in enumerate(produced):
                prompt = "Task: fix\n" + (SELF_HEAL_SENTENCE if index else "") + "\n"
                record = capture_record(
                    ["--output-format", "json", "--print", prompt],
                    "",
                    {
                        "NEXUS_BENCH_ARM": "with_nexus",
                        "NEXUS_BENCH_CAPTURE_KEY": "nexus-value-trust-002__1",
                        "NEXUS_BENCH_CAPTURE_RUN_ID": "run1",
                    },
                )
                path = write_record(record, str(capture))
                time.sleep(0.002)
                if response_dir:
                    write_response(response_dir, path.name, _agy_stdout(code) if code else "{}", 0)
                if code:
                    product_lane.record_model_candidate(
                        trace, code, "llm" if index == 0 else "llm_self_heal"
                    )
                else:
                    product_lane.record_failed_model_call(trace)
            if product_list is not None:
                trace["model_candidate_sha256s"] = product_list
            final = next((code for code in reversed(produced) if code), None)
            if timeout:
                raise subprocess.TimeoutExpired(cmd, timeout_sec)
            if final:
                Path(target_file).write_text(final, encoding="utf-8")
            payload = {
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "result": {
                    "elapsed_sec": 0.1,
                    "error": "pytest_failed",
                    "report": {
                        "attempt_count": len(produced),
                        "model_calls": len(produced),
                        "model_patch_generated": True,
                        "total_tokens": 100 * len(produced),
                        "winner_source": "llm" if produced.index(final) == 0 else "llm_self_heal",
                        "model_candidate_sha256": _sha(final),
                        "learning_trace": trace,
                    },
                },
            }
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return real_run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    row = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=120,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )
    row["mode"] = "with_nexus"
    assert len(envs) == 1, "one product subprocess per row (no probe, no rescue, no retry)"
    lane.rescore_rows([row], run_hidden=_plain_hidden, run_visible=_plain_visible)
    return row, envs


def _plain_hidden(
    code: str, target_file: str, hidden: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Test double for the confined hidden runner (#2211 not on this base): same scratch copy,
    plain pytest. The production path is ``confined_hidden_runner`` (confined only)."""

    with lane.scratch_task_dir(target_file, hidden, code) as test:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--maxfail=1",
                "-p",
                "no:cacheprovider",
                "--",
                test.name,
            ],
            cwd=test.parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )


def _plain_visible(
    code: str, _original: str, target_file: str, visible: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Test double for the seam's confined visible runner: no hidden test in the copy."""

    with lane.scratch_task_dir(target_file, visible, code) as test:
        (test.parent / "test_hidden.py").unlink(missing_ok=True)
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--maxfail=1",
                "-p",
                "no:cacheprovider",
                "--",
                test.name,
            ],
            cwd=test.parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )


def _bare_row(tmp_path: Path, monkeypatch, *, lane_name: str, answer_ok: bool) -> dict:
    from scripts.bench.capability_ab_runner import (
        _materialize_fixture,
        load_tasks,
        run_without_nexus,
    )

    monkeypatch.setenv("NEXUS_BENCH_LANE", lane_name)
    tasks = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")
    task = next(t for t in tasks if t.id == "nexus-value-trust-002")
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    original = Path(target_file).read_text(encoding="utf-8")
    snippet = next(
        line.strip() for line in original.splitlines() if line.strip().startswith("return")
    )
    replacement = (
        "return 'open' if not smoke_passed else ('resolved' if (semantic_evidence or {}).get('verified') is True else 'needs_evidence')"
        if answer_ok
        else "return 'resolved'"
    )

    def fake_agy(*, prompt: str, timeout_sec: int):
        answer = {
            "status": "ok",
            "operation": "replace",
            "target_snippet": snippet,
            "replacement": replacement,
        }
        return {**answer, "tokens_used": 50, "token_capture_status": "measured"}, json.dumps(answer)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_agy_patch", fake_agy)
    row = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=60,
        force_flow=None,
        mode="agy",
    )
    row["mode"] = "without_nexus"
    return lane.finalize_bare_row(row)


@pytest.mark.parametrize(
    "candidates, strict_solved, after_solved",
    [
        ([BAD_CLASSIFY, GOOD_CLASSIFY], False, True),  # self-heal repairs a wrong first answer
        ([GOOD_CLASSIFY], True, True),  # first answer right, nothing to treat
        ([BAD_CLASSIFY, BAD_CLASSIFY + "# still wrong\n"], False, False),
    ],
    ids=["repaired", "first_right", "still_wrong"],
)
def test_zero_model_both_lanes_produce_rows_and_first_attempt_equals_strict(
    tmp_path: Path, monkeypatch, candidates, strict_solved, after_solved
) -> None:
    strict_row, strict_envs = _with_nexus_row(
        tmp_path / "strict", monkeypatch, lane_name="strict", candidates=candidates
    )
    treated_row, treated_envs = _with_nexus_row(
        tmp_path / "treat", monkeypatch, lane_name="treatment", candidates=candidates
    )
    strict_bare = _bare_row(
        tmp_path / "bs", monkeypatch, lane_name="strict", answer_ok=strict_solved
    )
    treated_bare = _bare_row(
        tmp_path / "bt", monkeypatch, lane_name="treatment", answer_ok=strict_solved
    )

    # env: the strict lane is unchanged; the treatment lane only adds the treatment switches
    assert strict_envs[0]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "0"
    assert "NEXUS_BENCH_TREATMENT_LANE" not in strict_envs[0]
    assert "NEXUS_BENCH_RESPONSE_CAPTURE_DIR" not in strict_envs[0]
    assert treated_envs[0]["NEXUS_BENCH_TREATMENT_LANE"] == "1"
    assert treated_envs[0]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"
    assert (
        treated_envs[0]["NEXUS_SYMMETRIC_PROMPT"] == strict_envs[0]["NEXUS_SYMMETRIC_PROMPT"] == "1"
    )
    assert float(treated_envs[0]["NEXUS_BENCH_ROW_DEADLINE_EPOCH"]) <= time.time() + 120 + 1

    rows = [strict_row, strict_bare]
    treated = [treated_row, treated_bare]
    apply_strict_llm_baseline_classification(rows)
    apply_strict_llm_baseline_classification(treated)
    assert (
        strict_row["first_attempt"] is strict_solved
        and strict_row["after_treatment"] is strict_solved
    )
    # the treatment lane's first attempt is the strict lane's result for the same first candidate
    assert treated_row["first_attempt"] is strict_row["first_attempt"]
    assert treated_row["after_treatment"] is after_solved
    assert treated_row["first_model_candidate_sha256"] == _sha(candidates[0])
    assert treated_row["runner_candidate_sha256s"] == [_sha(code) for code in candidates]
    assert treated_row["model_calls"] == len(candidates) and treated_row["tokens"] == 100 * len(
        candidates
    )
    assert treated_row["treatment_rounds"] == len(candidates)
    expected_status = (
        "verified_as_delivered" if len(candidates) == 1 else "verified_confined_rescore"
    )
    assert treated_row["first_attempt_status"] == expected_status
    for bare in (strict_bare, treated_bare):
        assert bare["first_attempt"] is strict_solved and bare["after_treatment"] is strict_solved
    assert treated_bare["lane"] == "treatment" and treated_bare["bare_retries"] == 0
    if len(candidates) > 1:
        assert set(treated_row["treatment_visible_outputs"]) == {_sha(candidates[0])}


def test_first_attempt_rescore_never_writes_the_workspace(tmp_path: Path, monkeypatch) -> None:
    """G8: the first candidate is re-scored on a scratch copy; a candidate writing files only
    touches the copy, and the delivered file stays the final candidate."""

    writer = BAD_CLASSIFY + "open('SIDE_EFFECT.txt', 'w').write('x')\n"
    row, _ = _with_nexus_row(
        tmp_path, monkeypatch, lane_name="treatment", candidates=[writer, GOOD_CLASSIFY]
    )
    assert row["first_attempt_status"] == "verified_confined_rescore"
    assert row["first_attempt_hidden_passed"] is False and row["hidden_verifier_passed"] is True
    assert not list(tmp_path.rglob("SIDE_EFFECT.txt"))
    delivered = [
        p for p in tmp_path.rglob("target.py") if p.read_text(encoding="utf-8") == GOOD_CLASSIFY
    ]
    assert delivered


def test_failed_first_call_then_self_heal_is_not_a_first_attempt_solve(
    tmp_path: Path, monkeypatch
) -> None:
    """H1 end to end: call 1 returned nothing usable; strict scores not solved, so must first_attempt."""

    row, _ = _with_nexus_row(
        tmp_path, monkeypatch, lane_name="treatment", candidates=[None, GOOD_CLASSIFY]
    )
    apply_strict_llm_baseline_classification([row])
    assert row["first_attempt_status"] == "no_model_candidate"
    assert row["first_attempt"] is False


def test_product_list_reordered_is_first_attempt_unverifiable(tmp_path: Path, monkeypatch) -> None:
    """G3 probe: the product puts the winning later sha at index 0."""

    row, _ = _with_nexus_row(
        tmp_path,
        monkeypatch,
        lane_name="treatment",
        candidates=[BAD_CLASSIFY, GOOD_CLASSIFY],
        product_list=[_sha(GOOD_CLASSIFY), _sha(BAD_CLASSIFY)],
    )
    apply_strict_llm_baseline_classification([row])
    assert row["first_attempt_status"] == "first_attempt_unverifiable"
    assert row["first_attempt"] is False and row["after_treatment"] is False


def test_product_sha_without_a_captured_origin_makes_the_row_unverifiable(
    tmp_path: Path, monkeypatch
) -> None:
    """G4 probe: the product appends a sha no captured model response produced."""

    local = GOOD_CLASSIFY + "# local rescue\n"
    row, _ = _with_nexus_row(
        tmp_path,
        monkeypatch,
        lane_name="treatment",
        candidates=[BAD_CLASSIFY, GOOD_CLASSIFY],
        product_list=[_sha(BAD_CLASSIFY), _sha(GOOD_CLASSIFY), _sha(local)],
    )
    apply_strict_llm_baseline_classification([row])
    assert row["treatment_unverified_shas"] == [_sha(local)]
    assert row["treatment_unverifiable"] is True and row["after_treatment"] is False


def test_killed_subprocess_still_scores_the_first_attempt(tmp_path: Path, monkeypatch) -> None:
    """H2: at the row deadline the product never reports; the runner recovers call 1 from the capture."""

    row, _ = _with_nexus_row(
        tmp_path,
        monkeypatch,
        lane_name="treatment",
        candidates=[GOOD_CLASSIFY, BAD_CLASSIFY],
        timeout=True,
    )
    assert row["treatment_timeout"] is True and row["after_treatment_status"] == "not_run:timeout"
    assert row["model_calls"] == 2 and row["model_calls_source"] == "prompt_capture"
    assert row["first_attempt_status"] == "verified_confined_rescore"
    assert row["first_attempt_hidden_passed"] is True
    apply_strict_llm_baseline_classification([row])
    assert row["first_attempt"] is True and row["after_treatment"] is False


def test_no_response_capture_makes_the_first_attempt_unverifiable(tmp_path: Path) -> None:
    os.environ["NEXUS_BENCH_LANE"] = "treatment"
    os.environ.pop("NEXUS_BENCH_PROMPT_CAPTURE_DIR", None)

    def never(*_args):
        raise AssertionError("no verifier may run without a runner-derived candidate")

    row = {"model_candidate_sha256": _sha("x = 2\n"), "delivered_target_sha256": _sha("x = 2\n")}
    payload = {
        "result": {
            "report": {
                "learning_trace": {
                    "model_candidate_sha256s": [_sha("x = 1\n"), _sha("x = 2\n")],
                    "model_candidate_sources": ["llm", "llm_self_heal"],
                }
            }
        }
    }
    lane.finalize_with_nexus_row(
        row,
        payload,
        target_file=str(tmp_path / "t.py"),
        test_file=str(tmp_path / "test_v.py"),
        verification_test_file=str(tmp_path / "test_hidden.py"),
        original_source="x = 0\n",
        key="k__1",
        timeout_sec=10,
    )
    lane.rescore_rows([row], run_hidden=never, run_visible=never)
    assert lane.RESCORE_KEY not in row
    assert row["first_attempt_status"] == "first_attempt_unverifiable"
    assert row["treatment_unverifiable"] is True
    row.update({
        "mode": "with_nexus",
        "status": "SUCCESS",
        "model_calls": 2,
        "nexus_winner_source": "llm_self_heal",
    })
    apply_strict_llm_baseline_classification([row])
    assert row["first_attempt"] is False and row["after_treatment"] is False


def test_target_outside_the_test_directory_is_unverifiable_not_a_crash(tmp_path: Path) -> None:
    """L1/N2: a re-score that cannot run is a row-level status, never an exception out of the run.
    (The strict scorer copies only the test directory as well; both datasets co-locate target.py.)"""

    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_hidden.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    row: dict = {"treatment_first_consistent": True}
    job = {
        "target_file": str(tmp_path / "src" / "target.py"),
        "verification_test_file": str(test_dir / "test_hidden.py"),
        "timeout_sec": 10,
    }
    lane._first_attempt(
        row,
        job=job,
        entries=[{"kind": "stage1", "sha": _sha("a = 1\n"), "code": "a = 1\n"}],
        run_hidden=_plain_hidden,
    )
    assert row["first_attempt_status"] == "first_attempt_unverifiable"
    assert "target_outside_test_directory" in row["first_attempt_error"]
    assert row["first_attempt_hidden_passed"] is None


def test_early_audit_defers_round_classification_until_the_rescore(tmp_path: Path) -> None:
    rows = _rows()
    rows[1]["_treatment_rescore"] = {"target_file": "x"}
    rows[1]["treatment_visible_outputs"] = {}
    report = _audit(tmp_path, _round2(), rows=rows)
    assert (
        report["status"] == "PASS"
        and report["tasks"][0]["treatment_round_findings_deferred"] is True
    )
    rows[1].pop("_treatment_rescore")
    assert _audit(tmp_path / "f", _round2(), rows=rows)["status"] == "FAIL"


def _derive_setup(tmp_path: Path, monkeypatch, records: list[dict]) -> None:
    capture = tmp_path / "cap"
    responses = tmp_path / "cap.responses"
    capture.mkdir(mode=0o700, parents=True)
    responses.mkdir(mode=0o700, parents=True)
    monkeypatch.setenv("NEXUS_BENCH_PROMPT_CAPTURE_DIR", str(capture))
    monkeypatch.setenv("NEXUS_BENCH_RESPONSE_CAPTURE_DIR", str(responses))
    monkeypatch.setenv("NEXUS_BENCH_CAPTURE_RUN_ID", "r")
    for index, extra in enumerate(records):
        record = {
            **capture_record(
                extra.pop("argv", ["--output-format", "json", "--print", "Task: fix"]),
                "",
                {
                    "NEXUS_BENCH_ARM": "with_nexus",
                    "NEXUS_BENCH_CAPTURE_KEY": "k__1",
                    "NEXUS_BENCH_CAPTURE_RUN_ID": "r",
                },
            ),
            **extra,
        }
        path = write_record(record, str(capture))
        write_response(str(responses), path.name, _agy_stdout(f"x = {index}\n"), 0)


def test_forged_capture_records_make_the_row_unverifiable(tmp_path: Path, monkeypatch) -> None:
    """N3 probes: a record dated before the row, a broken sequence, a non-JSON-mode call."""

    start = time.time()
    _derive_setup(tmp_path / "ok", monkeypatch, [{}, {}])
    entries, error = lane.derive_runner_candidates(
        original_source="x = 9\n", key="k__1", row_start_epoch=start - 1
    )
    assert error == "" and [e["code"] for e in entries] == ["x = 0\n", "x = 1\n"]
    _derive_setup(tmp_path / "ts", monkeypatch, [{}, {"ts": 0.0}])
    assert lane.derive_runner_candidates(original_source="", key="k__1", row_start_epoch=start - 1)[
        1
    ].startswith("capture_record_before_row_start")
    _derive_setup(tmp_path / "seq", monkeypatch, [{}, {"seq": 0}])
    assert (
        lane.derive_runner_candidates(original_source="", key="k__1")[1]
        == "capture_sequence_broken"
    )
    _derive_setup(tmp_path / "txt", monkeypatch, [{"argv": ["--print", "Task: fix"]}])
    entries, error = lane.derive_runner_candidates(original_source="", key="k__1")
    assert (
        error == "" and entries[0]["error"] == "agy_not_json_output_mode" and not entries[0]["sha"]
    )


def test_plain_text_agy_output_is_refused_by_runner_and_runtime() -> None:
    """N4: in JSON output mode the pinned runtime requires the envelope (agy_envelope_missing);
    the runner uses the same parser, so plain text is refused on both sides."""

    import importlib

    transport = importlib.import_module("nexus_runtime.kernel.transport")
    plain = "def f():\n    return 2\n"
    assert transport.parse_agy_envelope(plain) is None
    assert lane.candidate_from_response("def f():\n    return 1\n", plain) == (
        "",
        "no_model_response",
    )


def test_candidate_from_response_uses_the_product_extraction() -> None:
    source = "def f():\n    return 1\n"
    edit = json.dumps({
        "status": "ok",
        "operation": "replace",
        "target_snippet": "return 1",
        "replacement": "return 2",
    })
    stdout = json.dumps({"response": edit})
    assert lane.candidate_from_response(source, stdout) == ("def f():\n    return 2\n", "")
    assert lane.candidate_from_response(source, json.dumps({"response": ""}))[0] == ""
    bad = json.dumps({
        "response": json.dumps({
            "operation": "replace",
            "target_snippet": "nope",
            "replacement": "x",
        })
    })
    assert lane.candidate_from_response(source, bad) == ("", "llm_target_snippet_not_unique")


# --------------------------------------------------------------------------- run_lane / analyze_run


def test_run_lane_builds_identical_commands_except_the_lane() -> None:
    from scripts.bench.run_lane import build_command

    strict, strict_env = build_command(lane="strict", run_id="r", python="py")
    treated, treated_env = build_command(
        lane="treatment", run_id="r", python="py", treatment_max_model_calls=3
    )
    assert strict[: strict.index("--lane")] == treated[: treated.index("--lane")]
    assert strict[strict.index("--lane") + 1] == "strict"
    assert treated[treated.index("--lane") :] == [
        "--lane",
        "treatment",
        "--treatment-max-model-calls",
        "3",
    ]
    for flag in (
        "--strict-llm-baseline",
        "--no-hidden-feedback",
        "--no-nexus-task-hints",
        "--counted-first-attempt",
    ):
        assert flag in strict and flag in treated
    assert strict_env["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "0"
    assert "NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL" not in treated_env
    with pytest.raises(ValueError):
        build_command(lane="bogus", run_id="r")


def test_run_lane_without_execute_only_prints(capsys) -> None:
    from scripts.bench.run_lane import main

    assert main(["--lane", "treatment", "--run-id", "dry"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert "--lane" in printed["argv"] and "treatment" in printed["argv"]


def test_analyze_run_reports_both_columns_paired_and_flags(tmp_path: Path, capsys) -> None:
    from scripts.bench.analyze_run import analyze, main

    rows_with = [
        _treated_row(task_id="t"),
        _treated_row(task_id="u", final_candidate_in_model_candidates=False),
    ]
    rows_without = [
        {
            "mode": "without_nexus",
            "task_id": "t",
            "trial_index": 1,
            "status": "FAILED",
            "model_calls": 1,
            "total_tokens": 10,
            "lane": "treatment",
        },
        {
            "mode": "without_nexus",
            "task_id": "u",
            "trial_index": 1,
            "status": "FAILED",
            "model_calls": 1,
            "total_tokens": 10,
            "lane": "treatment",
        },
    ]
    (tmp_path / "with_nexus_1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows_with), encoding="utf-8"
    )
    (tmp_path / "without_nexus_1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows_without), encoding="utf-8"
    )
    (tmp_path / "prompt_symmetry_audit.json").write_text(
        json.dumps({
            "status": "PASS",
            "lane": "treatment",
            "tasks": [{"key": "t__1", "with_nexus_calls": 3}],
        }),
        encoding="utf-8",
    )
    result = analyze(tmp_path)
    assert result["arms"]["with_nexus"]["first_attempt"] == 0
    assert result["arms"]["with_nexus"]["after_treatment"] == 1
    assert result["arms"]["bare"]["after_treatment"] == 0
    assert any("not among the row's model candidates" in flag for flag in result["flags"])
    assert any("captured calls 3 != row model_calls 2" in flag for flag in result["flags"])
    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "first_attempt" in out and "after_treatment" in out and "| t | 1 |" in out


def test_capture_wrapper_records_the_model_response_and_forwards_stdout(tmp_path: Path) -> None:
    """The response record the runner derives candidates from (treatment lane only)."""

    real = tmp_path / "agy-real"
    real.write_text(
        f"#!{sys.executable}\nimport json, sys\nprint(json.dumps({{'response': 'hello'}}))\n",
        encoding="utf-8",
    )
    real.chmod(0o755)
    capture = tmp_path / "cap"
    responses = tmp_path / "cap.responses"
    capture.mkdir(mode=0o700)
    responses.mkdir(mode=0o700)
    env = {
        **os.environ,
        "NEXUS_BENCH_PROMPT_CAPTURE_REAL": str(real),
        "NEXUS_BENCH_PROMPT_CAPTURE_DIR": str(capture),
        "NEXUS_BENCH_RESPONSE_CAPTURE_DIR": str(responses),
        "NEXUS_BENCH_ARM": "with_nexus",
        "NEXUS_BENCH_CAPTURE_KEY": "k__1",
        "NEXUS_BENCH_CAPTURE_RUN_ID": "r",
    }
    done = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bench" / "agy_prompt_capture.py"),
            "--print",
            "hi",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"response": "hello"}
    (prompt_file,) = list(capture.iterdir())
    record = json.loads((responses / prompt_file.name).read_text(encoding="utf-8"))
    assert json.loads(record["stdout"]) == {"response": "hello"} and record["returncode"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        "def classify(smoke_passed, semantic_evidence):\n    return ('closed'\n",
        "def classify(smoke_passed, semantic_evidence):\n    return '\\d'\n",
    ],
    ids=["syntax_error", "syntax_warning"],
)
def test_product_syntax_rejections_pass_the_round_audit(tmp_path: Path, bad: str) -> None:
    """R2-1: the failure tail of a real self-heal round after a syntax error/warning is exactly
    what the product's guard and executor print (shared helper), so the audit allows it."""

    from nexus.research.sprint_service import (
        executor_syntax_rejection,
        guard_syntax_rejection,
        syntax_rejection_lines,
    )

    lines = [guard_syntax_rejection(bad), executor_syntax_rejection(bad, "target.py")]
    assert set(filter(None, lines)) == syntax_rejection_lines(bad)
    tail = "\n".join(line for line in lines if line) + "\n" if any(lines) else ""
    rows = _rows(candidates={_sha(bad): bad, _sha(FINAL): FINAL})
    report = _audit(tmp_path, _round2(failure=tail, candidate=bad), rows=rows)
    assert report["status"] == "PASS", report["tasks"][0]["treatment_round_findings"]
    other = "def classify(smoke_passed, semantic_evidence):\n    return 'closed'\n"
    forged = _audit(
        tmp_path / "f",
        _round2(failure="syntax_error: return open unless verified\n", candidate=other),
        rows=_rows(candidates={_sha(other): other, _sha(FINAL): FINAL}),
    )
    assert forged["status"] == "FAIL"


def test_candidate_from_response_tolerates_leading_agy_warning_lines() -> None:
    """R2-2: the runner parses agy stdout with the product's transport parser."""

    source = "def f():\n    return 1\n"
    envelope = json.dumps({"response": json.dumps({"patch": "def f():\n    return 2\n"})})
    assert lane.candidate_from_response(source, f"Warning: update available\n{envelope}") == (
        "def f():\n    return 2\n",
        "",
    )


def test_scratch_copy_mirrors_the_strict_scorers_test_dir_copy(tmp_path: Path) -> None:
    """LOW-1/LOW-2: the re-score copy is the strict scorer's shape (regular files of the test
    dir, no dotfiles, no subdirs) with the candidate as target; the visible re-run is the seam's
    confined runner, which never copies a hidden test. Checked on trust-002."""

    from scripts.bench.capability_ab_runner import _materialize_fixture, load_tasks

    tasks = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")
    task = next(t for t in tasks if t.id == "nexus-value-trust-002")
    target_file, visible = _materialize_fixture(tmp_path, task)
    (Path(visible).parent / ".hidden_dotfile").write_text("x", encoding="utf-8")
    (Path(visible).parent / "sub").mkdir()
    hidden = str(Path(visible).with_name("test_hidden.py"))
    with lane.scratch_task_dir(target_file, hidden, GOOD_CLASSIFY) as test:
        names = sorted(p.name for p in test.parent.iterdir())
        assert names == ["target.py", "test_hidden.py", "test_visible.py"]
        assert (test.parent / "target.py").read_text(encoding="utf-8") == GOOD_CLASSIFY
    done = _plain_hidden(GOOD_CLASSIFY, target_file, hidden, 60)
    assert done.returncode == 0, done.stdout
    assert Path(target_file).read_text(encoding="utf-8") != GOOD_CLASSIFY  # workspace untouched


def test_hyper_counts_only_with_more_than_one_stage1_candidate() -> None:
    """LOW-3: a stage-1 call plus a self-heal round is self_heal, not hyper."""

    hyper = {
        "name": "hyper",
        "attestation": "real",
        "attestation_source": "unified_capability_projection",
        "attestation_refs_resolved": True,
        "attestation_disposition": {"kind": "succeeded"},
        "selected": True,
        "invoked": True,
        "evidence_refs": ["ref1"],
        "claim_boundary": {"simulated": False},
    }
    row = _treated_row(treatment_rounds=2, capability_receipts=[hyper])
    lane.attest_row(row, {"with_nexus_calls": 2, "self_heal_rounds_observed": 1})
    assert "hyper" not in row["treatment_applied"]
    a, b = _sha("a"), _sha("b")
    pool = _treated_row(
        runner_candidate_sha256s=[a, b],
        runner_candidate_kinds=["stage1", "stage1"],
        capability_receipts=[hyper],
    )
    lane.attest_row(pool, {"with_nexus_calls": 2})
    assert {"hyper", "multi_candidate"} <= set(pool["treatment_applied"])


# --------------------------------------------------------------------------- merged #2211: real wiring


@pytest.fixture
def isolated_staging(tmp_path: Path, monkeypatch):
    """#2211 hidden-test staging with a private parent (same isolation as its own tests)."""

    from scripts.bench import hidden_test_staging as staging_mod

    monkeypatch.setattr(staging_mod, "_STAGING_PARENT", tmp_path / "cache" / "nexus-bench-hidden")
    for name in ("_ACTIVE", "_RUN_ROOTS", "_IN_MEMORY_SHAS"):
        monkeypatch.setattr(staging_mod, name, {})
    monkeypatch.setattr(staging_mod, "_QUARANTINED", set())
    monkeypatch.setattr(staging_mod, "_RUN_ABORT", [])
    monkeypatch.setattr(staging_mod, "_RUN_RECORD_PATH", [])
    yield staging_mod

    def unlock(path: Path) -> None:
        if path.is_symlink() or not path.exists():
            return
        if path.is_dir():
            os.chmod(path, 0o700)
            for child in path.iterdir():
                unlock(child)
        else:
            os.chmod(path, 0o600)

    unlock(tmp_path)


def _real_barrier() -> bool:
    from nexus.engine.sandboxed_lane import os_sandbox_available

    pytest_isolated = (
        subprocess.run(
            [sys.executable, "-I", "-c", "import pytest"], capture_output=True, check=False
        ).returncode
        == 0
    )
    return bool(os_sandbox_available()) and pytest_isolated


HARD_TARGET_BAD = "def level(value):\n    return value\n"
HARD_TARGET_GOOD = "def level(value):\n    return value if value else 'unknown'\n"
HARD_IMPORT = (
    "import importlib.util\nfrom pathlib import Path\n"
    "_S = importlib.util.spec_from_file_location('t', Path(__file__).resolve().parent / 'target.py')\n"
    "_M = importlib.util.module_from_spec(_S)\n_S.loader.exec_module(_M)\n"
)


def _hard_v1_shaped_task(root: Path):
    """A hard_v1-shaped fixture: bench_fixtures/online_ab_hard_v1/<dir>/{target,test_visible,test_hidden}.py."""

    from scripts.bench.capability_ab_runner import CapabilityTask

    case = root / "bench_fixtures" / "online_ab_hard_v1" / "level-blank"
    case.mkdir(parents=True)
    (case / "target.py").write_text(
        "def level(value):\n    raise NotImplementedError\n", encoding="utf-8"
    )
    (case / "test_visible.py").write_text(
        HARD_IMPORT + "\ndef test_v():\n    assert _M.level('x') == 'x'\n", encoding="utf-8"
    )
    (case / "test_hidden.py").write_text(
        HARD_IMPORT + "\ndef test_h():\n    assert _M.level('') == 'unknown'\n", encoding="utf-8"
    )
    rel = "bench_fixtures/online_ab_hard_v1/level-blank"
    task = CapabilityTask(
        id="oabh-level-blank",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Blank levels map to unknown.",
        target_file=f"{rel}/target.py",
        test_file=f"{rel}/test_visible.py",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        hidden_test_file=f"{rel}/test_hidden.py",
    )
    return task, str(case / "target.py"), str(case / "test_visible.py")


@pytest.mark.parametrize("shape", ["p16", "hard_v1"])
def test_counted_treatment_row_inside_staging_with_confined_rescore(
    tmp_path: Path, monkeypatch, isolated_staging, shape: str
) -> None:
    """Merged #2211, zero model calls: the with-Nexus row runs inside ``staged_hidden_test`` (the
    hidden test is absent while the product runs), then the first-attempt re-score goes through
    the strict scorer's confined ``run_pytest_dir_copy`` and the visible re-run through the seam's
    ``run_visible_test_confined``. Without an OS barrier (Linux CI) both refuse: never unconfined."""

    from scripts.bench.capability_ab_runner import _materialize_fixture, load_tasks, run_with_nexus
    from scripts.bench.capability_ab_runner import _run_process_group as real_run_process_group

    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    ws = tmp_path / "ws"  # the workspace; the staging parent (tmp_path/cache) stays outside it
    ws.mkdir()
    capture = tmp_path / "captures"
    capture.mkdir(mode=0o700)
    for name, value in {
        "NEXUS_BENCH_PROMPT_CAPTURE_DIR": str(capture),
        "NEXUS_BENCH_CAPTURE_RUN_ID": "run1",
        "NEXUS_BENCH_ARM": "with_nexus",
        "NEXUS_BENCH_NO_TASK_HINTS": "1",
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_SYMMETRIC_PROMPT": "1",
        "NEXUS_BENCH_LANE": "treatment",
        "NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS": "4",
        "NEXUS_BENCH_COUNTED_FIRST_ATTEMPT": "1",
        "NEXUS_BENCH_NO_HIDDEN_FEEDBACK": "1",
        "NEXUS_BENCH_DISABLE_HIDDEN_RETRY": "1",
        "NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE": "1",
    }.items():
        monkeypatch.setenv(name, value)
    if shape == "p16":
        tasks = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")
        task = next(t for t in tasks if t.id == "nexus-value-trust-002")
        target_file, visible = _materialize_fixture(ws, task)
        bad, good = BAD_CLASSIFY, GOOD_CLASSIFY
    else:
        task, target_file, visible = _hard_v1_shaped_task(ws)
        bad, good = HARD_TARGET_BAD, HARD_TARGET_GOOD
    key = f"{task.id}__{task.trial_index}"
    monkeypatch.setenv("NEXUS_BENCH_CAPTURE_KEY", key)
    hidden = Path(visible).with_name("test_hidden.py")
    seen_absent: list[bool] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            seen_absent.append(not hidden.exists())  # staged out for the whole product run
            trace: dict = {}
            for index, code in enumerate([bad, good]):
                prompt = "Task: fix\n" + (SELF_HEAL_SENTENCE if index else "") + "\n"
                record = capture_record(
                    ["--output-format", "json", "--print", prompt],
                    "",
                    {
                        "NEXUS_BENCH_ARM": "with_nexus",
                        "NEXUS_BENCH_CAPTURE_KEY": key,
                        "NEXUS_BENCH_CAPTURE_RUN_ID": "run1",
                    },
                )
                path = write_record(record, str(capture))
                write_response(
                    env["NEXUS_BENCH_RESPONSE_CAPTURE_DIR"], path.name, _agy_stdout(code), 0
                )
                product_lane.record_model_candidate(
                    trace, code, "llm" if index == 0 else "llm_self_heal"
                )
            Path(target_file).write_text(good, encoding="utf-8")
            payload = {
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "result": {
                    "elapsed_sec": 0.1,
                    "error": "pytest_failed",
                    "report": {
                        "attempt_count": 2,
                        "model_calls": 2,
                        "model_patch_generated": True,
                        "total_tokens": 200,
                        "winner_source": "llm_self_heal",
                        "model_candidate_sha256": _sha(good),
                        "learning_trace": trace,
                    },
                },
            }
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return real_run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group
    )
    with isolated_staging.staged_hidden_test(
        enabled=True,
        repo_root=ws,
        test_file=visible,
        task_id=task.id,
        trial_index=task.trial_index,
    ) as staging:
        assert staging is not None and not hidden.exists()
        row = run_with_nexus(
            repo_root=ws,
            task=task,
            target_file=target_file,
            test_file=visible,
            timeout_sec=120,
            force_flow="hyper_sprint",
            runner_mode="subprocess",
            with_llm_mode="all",
            strict_llm_baseline=True,
        )
    assert hidden.exists() and seen_absent == [True]
    row["mode"] = "with_nexus"
    lane.rescore_rows(
        [row],
        run_hidden=lane.confined_hidden_runner(ws),
        run_visible=lane.confined_visible_runner(ws),
    )
    outputs = row["treatment_visible_outputs"]
    assert set(outputs) == {_sha(bad)} and outputs[_sha(bad)].strip()  # non-empty for both shapes
    assert row["runner_candidate_sha256s"] == [_sha(bad), _sha(good)]
    assert row["model_calls"] == 2 and row["tokens"] == 200
    apply_strict_llm_baseline_classification([row])
    if _real_barrier():
        assert row["first_attempt_status"] == "verified_confined_rescore", row.get(
            "first_attempt_error"
        )
        assert row["first_attempt_hidden_passed"] is False and row["first_attempt"] is False
        assert row["hidden_verifier_passed"] is True and row["after_treatment"] is True
        # the visible test really ran on the first candidate (confined)
        assert ("failed" if shape == "p16" else "passed") in outputs[_sha(bad)]
    else:
        assert row["first_attempt_status"] == "first_attempt_unverifiable"
        assert "confinement_unavailable" in outputs[_sha(bad)]
        assert row["first_attempt"] is False


def test_round_two_audit_accepts_the_real_confined_visible_output(tmp_path: Path) -> None:
    """The [FAILURE] tail the product sends (seam ``run_visible_test_confined`` stdout) matches
    the runner's own re-run of the same function after normalisation; a hint still fails."""

    from nexus.services import post_candidate_seam as seam

    bad = "def classify(smoke_passed, semantic_evidence):\n    return 'closed'\n"
    case = tmp_path / "ws" / ".nexus" / "bench_cases" / "nexus-value-trust-002"
    case.mkdir(parents=True)
    (case / "target.py").write_text(SOURCE, encoding="utf-8")
    (case / "test_visible.py").write_text(
        HARD_IMPORT
        + "\ndef test_v():\n    assert _M.classify(False, {'verified': True}) == 'open'\n",
        encoding="utf-8",
    )
    (case / "test_hidden.py").write_text(HIDDEN, encoding="utf-8")
    runner = lane.confined_visible_runner(tmp_path / "ws")
    recorded = runner(bad, SOURCE, str(case / "target.py"), str(case / "test_visible.py"), 60)
    product, _executed = seam.run_visible_test_confined(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=SOURCE,
        candidate_code=bad,
        timeout_sec=60,
        workspace_root=tmp_path / "ws",
    )
    tail = (product.stdout or product.stderr or "")[-1200:]
    rows = _rows(candidates={_sha(bad): bad, _sha(FINAL): FINAL})
    rows[1]["treatment_visible_outputs"] = {_sha(bad): f"{recorded.stdout}\n{recorded.stderr}"}
    report = _audit(tmp_path / "a", _round2(failure=tail, candidate=bad), rows=rows)
    assert report["status"] == "PASS", report["tasks"][0]["treatment_round_findings"]
    hinted = _audit(
        tmp_path / "h",
        _round2(failure=tail, candidate=bad, extra="hint: return open first.\n"),
        rows=rows,
    )
    assert hinted["status"] == "FAIL"


def test_real_seam_receipts_count_only_when_attested_with_seam_evidence(tmp_path: Path) -> None:
    """treatment_applied takes sandbox/ultra_review from #2211's seam receipts overlaid by #2212's
    projection (attested real, trigger post_candidate_seam:*, evidence ids); a receipt with the
    same attestation but no seam trigger does not count."""

    from nexus.research.flow.unified_capability_projection import (
        overlay_unified_capability_receipts,
        project_unified_capability_stages,
    )
    from nexus.services import post_candidate_seam as seam
    from tests.services.test_post_candidate_seam import CANDIDATE, ORIGINAL, _case, _runtime_receipt

    case = _case(tmp_path)

    def factory(name: str):
        def invoke(context):
            return {
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"ev_{name}_run_001"],
                "physical_callable": f"tests.fake.{name}",
                "response": {
                    "status": "SUCCEEDED",
                    "outcome": {
                        "semantic_status": "SUCCEEDED",
                        "exit_code": 0,
                        "stdout_sha256": "ab" * 32,
                        "output_tail": "1 passed",
                        "simulated": False,
                        "sandbox_executed": True,
                        "confined": True,
                        "executed_checks": ["visible_test"],
                        "result": "PASS",
                    },
                },
            }

        return invoke

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("sandbox", "ultra_review"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        invoker_factory=factory,
    )
    flow = overlay_unified_capability_receipts(
        [{"name": n, "selected": True, "invoked": False} for n in ("sandbox", "ultra_review")],
        project_unified_capability_stages([receipt]),
    )
    row = _treated_row(capability_receipts=flow)
    lane.attest_row(row, {"with_nexus_calls": 2, "self_heal_rounds_observed": 1})
    assert {"sandbox", "ultra_review"} <= set(row["treatment_applied"])
    stripped = [{**item, "trigger_source": ""} for item in flow]
    plain = _treated_row(capability_receipts=stripped)
    lane.attest_row(plain, {"with_nexus_calls": 2, "self_heal_rounds_observed": 1})
    assert not {"sandbox", "ultra_review"} & set(plain["treatment_applied"])


def test_lane_gate_passes_on_the_merged_tree_only_with_confinement(
    monkeypatch, tmp_path: Path
) -> None:
    """With #2211 merged the real modules satisfy the gate; NEXUS_CONFINE_VISIBLE_TEST must be 1
    (the runner sets it for the counted strict configuration the lane requires)."""

    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "0")
    assert lane.hidden_staging_ready(_fair_args())[0] is False
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    assert lane.hidden_staging_ready(_fair_args()) == (True, "")
    seen = _cli(monkeypatch, tmp_path, *FAIR_CLI, "--lane", "treatment")  # real gate, no fixture
    assert seen["lane"] == "treatment"
    assert os.environ.get("NEXUS_CONFINE_VISIBLE_TEST") == "1"


def test_treatment_replay_proof_passes_self_heal_and_fails_a_hint(tmp_path: Path) -> None:
    """The 8th zero-model proof assertion: replaying a run's captured bare + round-1 prompts with a
    synthetic self-heal round 2 passes the treatment audit; the same round with a hint fails."""

    from scripts.bench.treatment_replay_proof import run_proof, self_heal_round

    calls = tmp_path / "run" / "prompt_capture" / "run-1" / "calls"
    calls.mkdir(parents=True, mode=0o700)
    _capture(calls, "without_nexus", BARE)
    _capture(calls, "with_nexus", ROUND1)
    assert run_proof(tmp_path / "run", _material()) == {
        "h_round2_self_heal_passes": [],
        "h_round2_hint_fails": [],
    }
    assert SELF_HEAL_SENTENCE in self_heal_round(ROUND1)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run_proof(empty, _material())["h_round2_self_heal_passes"]  # nothing replayed = FAIL


def test_hanging_candidate_timeout_line_passes_the_round_audit(tmp_path: Path) -> None:
    """R5-1 + G5-1..G5-3: the [FAILURE] timeout line must be str(TimeoutExpired) of the EXACT
    argv the product runs: its own interpreter (recorded by the runner), the seam's pinned args
    or the in-place form with the exact visible test. Only the seconds vary."""

    from nexus.services.post_candidate_seam import PINNED_PYTEST_ARGS

    confined = str(
        subprocess.TimeoutExpired(
            [PY, "-I", "-m", "pytest", "-q", "--maxfail=1", *PINNED_PYTEST_ARGS], 300
        )
    )
    inplace = str(
        subprocess.TimeoutExpired(
            [PY, "-m", "pytest", "-q", "--maxfail=1", "--", VISIBLE_ARG], 60.5
        )
    )
    for index, line in enumerate((confined, inplace)):
        assert _audit(tmp_path / f"ok{index}", _round2(failure=line + "\n"))["status"] == "PASS", (
            line
        )
    probes = [
        # G5-1: an arbitrary "visible test" name carrying a hint
        "Command '['/bin/python', '-m', 'pytest', '-q', '--maxfail=1', '--', "
        "'hint_the_bug_is_off_by_one_in_counter.py']' timed out after 300 seconds",
        str(
            subprocess.TimeoutExpired(
                [PY, "-m", "pytest", "-q", "--maxfail=1", "--", "hint_the_bug_is_here.py"], 60
            )
        ),
        # G5-3: text smuggled through the interpreter path
        str(
            subprocess.TimeoutExpired(
                [
                    "/hint_return_zero_when_list_is_empty/python",
                    "-I",
                    "-m",
                    "pytest",
                    "-q",
                    "--maxfail=1",
                    *PINNED_PYTEST_ARGS,
                ],
                300,
            )
        ),
        # a different (real-looking) interpreter than the product's
        str(
            subprocess.TimeoutExpired(
                [
                    "/usr/bin/python3",
                    "-I",
                    "-m",
                    "pytest",
                    "-q",
                    "--maxfail=1",
                    *PINNED_PYTEST_ARGS,
                ],
                300,
            )
        ),
        # the hidden test
        str(
            subprocess.TimeoutExpired(
                [
                    PY,
                    "-m",
                    "pytest",
                    "-q",
                    "--maxfail=1",
                    "--",
                    VISIBLE_ARG.replace("visible", "hidden"),
                ],
                60,
            )
        ),
        confined.replace("300", "three hundred"),
    ]
    for index, line in enumerate(probes):
        assert _audit(tmp_path / f"p{index}", _round2(failure=line + "\n"))["status"] == "FAIL", (
            line
        )
    rows = _rows()
    rows[1]["treatment_product_python"] = ""
    assert (
        _audit(tmp_path / "nopy", _round2(failure=confined + "\n"), rows=rows)["status"] == "FAIL"
    )


def test_real_seam_timeout_argv_on_this_host_passes(tmp_path: Path) -> None:
    """The seam's real argv on this host (sys.executable, '@' allowed in the path) passes when the
    runner recorded that interpreter as the product's."""

    from nexus.services.post_candidate_seam import PINNED_PYTEST_ARGS

    real = str(
        subprocess.TimeoutExpired(
            [sys.executable, "-I", "-m", "pytest", "-q", "--maxfail=1", *PINNED_PYTEST_ARGS], 300
        )
    )
    rows = _rows()
    rows[1]["treatment_product_python"] = sys.executable
    assert _audit(tmp_path, _round2(failure=real + "\n"), rows=rows)["status"] == "PASS"
    assert lane.product_interpreter("uv", tmp_path) == ""
    assert lane.product_interpreter(".venv/bin/python", tmp_path) == str(
        tmp_path / ".venv" / "bin" / "python"
    )
    assert lane.product_interpreter(sys.executable, tmp_path) == sys.executable


def test_visible_rerun_timeout_records_the_timeout_line() -> None:
    """R5-1: the runner's own visible re-run of a hanging candidate records str(TimeoutExpired)."""

    argv = [sys.executable, "-I", "-m", "pytest", "-q"]

    def hang(*_args):
        raise subprocess.TimeoutExpired(argv, 7)

    entries = [
        {"kind": "stage1", "sha": _sha("a"), "code": "a"},
        {"kind": "self_heal", "sha": _sha("b"), "code": "b"},
    ]
    out = lane._visible_outputs(entries, job={"timeout_sec": 7}, run_visible=hang)
    assert out == {_sha("a"): str(subprocess.TimeoutExpired(argv, 7))}


def test_later_round_new_sprint_attempt_and_failure_sensor_are_allowed(tmp_path: Path) -> None:
    """From the wrong-then-right proof run: round 2 is a new sprint attempt (boundary task_id
    ...-s10000-a1), the planner adds semantic_failure_sensor, and the model-context block echoes
    the round's task text (task_desc + the self-heal block, capped)."""

    from scripts.bench.prompt_symmetry_audit import _round_task_text_ok, _schema_findings

    boundary1 = "NEXUS_SESSION_BOUNDARY_V1 task_id=sprint-aaaaaaaaaaaa-s0-a1 task_type=repair Treat this as an isolated task. Do not use facts from prior turns."
    head1 = NEXUS_HEAD.replace(
        NO_TOOLS_PREFIX + "\n\n", NO_TOOLS_PREFIX + "\n\n" + boundary1 + "\n\n"
    )
    round1 = head1 + "\n[TASK]\n" + BARE.replace(NO_TOOLS_PREFIX, "")
    round2 = _round2().replace(NEXUS_HEAD, head1.replace("-s0-a1", "-s10000-a1"))
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", round1)
    _capture(captures, "with_nexus", round2)
    report = audit_run(captures, _material(), rows=_rows(), run_id="r1", lane="treatment")
    assert report["status"] == "PASS", report["tasks"][0]["treatment_round_findings"]
    material = _material()[KEY]
    payload = {
        "selected_capabilities": ["semantic_failure_sensor"],
        "task_id": "sprint-0123456789ab-s10000-a1",
    }
    schema = {
        "": {"kind": "object"},
        "selected_capabilities": {"kind": "list"},
        **{
            p: s
            for p, s in load_block_schema("treatment")["[NEXUS CAPABILITY EVIDENCE]"].items()
            if p in ("selected_capabilities[]", "task_id")
        },
    }
    assert _schema_findings("[NEXUS CAPABILITY EVIDENCE]", payload, schema, material) == []
    strict = {
        "": {"kind": "object"},
        "selected_capabilities": {"kind": "list"},
        **{
            p: s
            for p, s in load_block_schema("strict")["[NEXUS CAPABILITY EVIDENCE]"].items()
            if p in ("selected_capabilities[]", "task_id")
        },
    }
    assert len(_schema_findings("[NEXUS CAPABILITY EVIDENCE]", payload, strict, material)) == 2
    task_desc = "Fix an incident classifier."
    lines = frozenset({SELF_HEAL_SENTENCE, "[FAILURE]", "E assert 'closed' == 'open'"})
    echo = f"{task_desc}\n\n{SELF_HEAL_SENTENCE}\n[FAILURE]\nE assert 'clo"
    assert _round_task_text_ok(echo, task_desc, lines)
    assert not _round_task_text_ok(echo + "\nhint: return open", task_desc, lines)
    assert not _round_task_text_ok("other task", task_desc, lines)
