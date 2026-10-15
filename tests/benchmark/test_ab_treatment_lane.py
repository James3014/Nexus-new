"""Wiring plan PR-3: the online A/B treatment lane (first attempt vs after treatment).

The treatment lane keeps every information-fairness rule of the strict lane (no hidden feedback,
no task hints, no local/deterministic solve, same model and per-call cap, one row deadline,
captured-prompt audit of EVERY call) and turns the product's treatments on for the with-Nexus
arm only. Rows carry ``first_attempt`` (the first model candidate scored exactly like the strict
lane) and ``after_treatment`` (the delivered candidate), plus model calls and tokens.
"""

from __future__ import annotations

import argparse
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
from scripts.bench.agy_prompt_capture import capture_record, write_record
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
    lane_scorecard,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_environ():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


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
    assert lane.with_nexus_env_overrides(deadline_epoch=time.time() + 60, archive_dir="/x") == {}


def test_treatment_lane_with_every_fairness_flag_is_accepted() -> None:
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
        ({"force_flow": "baseline"}, "--force-flow baseline"),
        ({"without_mode": "gemini"}, "--without-mode agy"),
        ({"with_llm_mode": "off"}, "--with-llm-mode"),
        ({"treatment_max_model_calls": 0}, "--treatment-max-model-calls"),
        ({"treatment_max_model_calls": 99}, "--treatment-max-model-calls"),
        ({"bare_retries": 2}, "--bare-retries"),
    ],
)
def test_treatment_lane_refuses_flags_that_break_fairness(override, needle) -> None:
    errors = lane.validate_lane_args(_fair_args(**override))
    assert errors and any(needle in error for error in errors), errors


def test_strict_lane_refuses_treatment_only_knobs() -> None:
    assert lane.validate_lane_args(_fair_args(lane="strict", treatment_max_model_calls=3))
    assert lane.validate_lane_args(_fair_args(lane="strict", bare_retries=1))


@pytest.mark.parametrize("name", ["NEXUS_ONLINE_LOCAL_ASSIST", "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED"])
def test_treatment_lane_refuses_local_and_external_paths(monkeypatch, name) -> None:
    monkeypatch.setenv(name, "1")
    assert any(name in error for error in lane.validate_lane_args(_fair_args()))


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


def test_cli_lane_treatment_reaches_the_run_with_the_lane_set(monkeypatch, tmp_path: Path) -> None:
    seen = _cli(monkeypatch, tmp_path, *FAIR_CLI, "--lane", "treatment")
    assert seen == {"lane": "treatment", "force_flow": "hyper_sprint", "no_hidden_feedback": "1"}
    default = _cli(monkeypatch, tmp_path, *FAIR_CLI)
    assert default["lane"] == "strict" and default["force_flow"] == "auto"


@pytest.mark.parametrize(
    "flags",
    [
        ("--lane", "treatment"),  # no strict baseline at all
        (*FAIR_CLI, "--lane", "treatment", "--allow-nexus-treatment"),
        (*FAIR_CLI, "--lane", "treatment", "--nexus-only"),
        (*FAIR_CLI, "--lane", "treatment", "--force-flow", "baseline"),
        (*FAIR_CLI, "--bare-retries", "1"),
        (*FAIR_CLI, "--treatment-max-model-calls", "3"),
    ],
)
def test_cli_refuses_unfair_lane_combinations(monkeypatch, tmp_path: Path, flags) -> None:
    with pytest.raises(SystemExit) as exc:
        _cli(monkeypatch, tmp_path, *flags)
    assert exc.value.code == 2


def test_treatment_env_turns_treatments_on_and_keeps_the_fairness_pins(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BENCH_LANE", "treatment")
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "3")
    deadline = time.time() + 120
    env = lane.with_nexus_env_overrides(deadline_epoch=deadline, archive_dir="/tmp/a")
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
    assert env["NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR"] == "/tmp/a"


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


def test_record_model_candidate_keeps_order_and_archives_bytes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR", str(tmp_path))
    trace: dict = {}
    first = product_lane.record_model_candidate(trace, "a = 1\n", "llm")
    second = product_lane.record_model_candidate(trace, "a = 2\n", "llm_self_heal")
    assert trace["model_candidate_sha256s"] == [first, second]
    assert trace["model_candidate_sources"] == ["llm", "llm_self_heal"]
    assert trace["first_model_candidate_sha256"] == first
    assert (tmp_path / f"{first}.txt").read_text(encoding="utf-8") == "a = 1\n"
    assert lane.read_archived_candidate(str(tmp_path), second) == "a = 2\n"
    (tmp_path / f"{second}.txt").write_text("tampered", encoding="utf-8")
    assert lane.read_archived_candidate(str(tmp_path), second) is None


def test_one_row_deadline_and_call_budget_cover_every_round(monkeypatch) -> None:
    trace: dict = {}
    monkeypatch.delenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", raising=False)
    monkeypatch.delenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", raising=False)
    assert product_lane.treatment_round_allowed(trace, "self_heal", 3) is True
    now = time.time()
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(now + 30))
    assert product_lane.row_deadline_allows_round(trace, "self_heal", now=now) is False
    assert trace["treatment_rounds_skipped_row_deadline"] == ["self_heal"]
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(now + 600))
    assert product_lane.row_deadline_allows_round(trace, "candidate_1", now=now) is True
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", "not-a-number")
    assert product_lane.row_deadline_allows_round(trace, "x") is False
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(time.time() + 600))
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "2")
    assert product_lane.treatment_round_allowed(trace, "self_heal", 1) is True
    assert product_lane.treatment_round_allowed(trace, "candidate_2", 2) is False
    assert trace["treatment_rounds_skipped_call_budget"] == ["candidate_2"]


def _sprint(monkeypatch, tmp_path: Path, *, treatment: bool, first: str, repair: str):
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
            code = first if len(calls) == 1 else repair
            return code, {"source": "llm", "model_calls": 1, "tokens_used": 7}

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

    archive = tmp_path / "archive"
    archive.mkdir()
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR", str(archive))
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    if treatment:
        monkeypatch.setenv("NEXUS_BENCH_TREATMENT_LANE", "1")
    else:
        monkeypatch.delenv("NEXUS_BENCH_TREATMENT_LANE", raising=False)
    monkeypatch.setattr(sprint_service, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(sprint_service, "SprintExecutor", FakeExecutor)
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
    return run_hyper_sprint(repo_root=tmp_path, config=cfg), calls, archive


BAD_VALUE = "def value():\n    return 3\n"
GOOD_VALUE = "def value():\n    return 2\n"


def test_sprint_treatment_lane_self_heals_and_records_every_model_candidate(
    monkeypatch, tmp_path: Path
) -> None:
    res, calls, archive = _sprint(
        monkeypatch, tmp_path, treatment=True, first=BAD_VALUE, repair=GOOD_VALUE
    )
    trace = res.learning_trace
    assert len(calls) == 2
    assert trace["model_candidate_sha256s"] == [_sha(BAD_VALUE), _sha(GOOD_VALUE)]
    assert trace["model_candidate_sources"] == ["llm", "llm_self_heal"]
    assert trace["first_model_candidate_sha256"] == _sha(BAD_VALUE)
    assert {p.name for p in archive.iterdir()} == {
        f"{_sha(BAD_VALUE)}.txt",
        f"{_sha(GOOD_VALUE)}.txt",
    }
    repair_task = calls[1]["task"]
    assert SELF_HEAL_SENTENCE in repair_task and "[FAILURE]" in repair_task
    # The local support candidate never reaches the audited prompt.
    assert "[NEXUS LOCAL SUPPORT CANDIDATE]" not in repair_task
    assert res.winner_source == "llm_self_heal" and res.patch == GOOD_VALUE


def test_sprint_strict_lane_stays_at_one_model_call(monkeypatch, tmp_path: Path) -> None:
    res, calls, _archive = _sprint(
        monkeypatch, tmp_path, treatment=False, first=BAD_VALUE, repair=GOOD_VALUE
    )
    assert len(calls) == 1
    assert res.learning_trace["model_candidate_sha256s"] == [_sha(BAD_VALUE)]


def test_sprint_treatment_round_skipped_near_the_row_deadline(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_BENCH_ROW_DEADLINE_EPOCH", str(time.time() + 5))
    res, calls, _archive = _sprint(
        monkeypatch, tmp_path, treatment=True, first=BAD_VALUE, repair=GOOD_VALUE
    )
    assert len(calls) == 1
    assert res.learning_trace["treatment_rounds_skipped_row_deadline"] == ["self_heal"]


def test_sprint_treatment_round_skipped_at_the_call_budget(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "1")
    res, calls, _archive = _sprint(
        monkeypatch, tmp_path, treatment=True, first=BAD_VALUE, repair=GOOD_VALUE
    )
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
# Round-1 model candidate: fails the visible test and happens to contain a hidden literal (the
# model's own guess). Quoting it back in round 2 is model output, not a leak.
CANDIDATE1 = "def classify(smoke_passed, semantic_evidence):\n    return 'needs_evidence'\n"
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
    "/tmp/run-abc/case/test_visible.py:2: AssertionError\n"
    "E       AssertionError: assert 'needs_evidence' == 'open'\n"
    "1 failed in 0.03s\n"
)


def _round2(failure: str = "", *, candidate: str = CANDIDATE1, extra: str = "") -> str:
    tail = failure or (
        "_ test_v _\n"
        "/private/var/folders/x/case/test_visible.py:2: AssertionError\n"
        "E       AssertionError: assert 'needs_evidence' == 'open'\n"
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


def _rows(archive: Path, *, model_calls: int = 2, max_calls: int = 4) -> list[dict]:
    final = SOURCE.replace("'open'", "'resolved'")
    shas = [_sha(CANDIDATE1), _sha(final)]
    archive.mkdir(exist_ok=True)
    (archive / f"{shas[0]}.txt").write_text(CANDIDATE1, encoding="utf-8")
    (archive / f"{shas[1]}.txt").write_text(final, encoding="utf-8")
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
            "model_candidate_sha256s": shas,
            "treatment_candidate_archive": str(archive),
            "treatment_visible_outputs": {shas[0]: VISIBLE_OUTPUT},
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
    tmp_path: Path, round2: str | None, *, lane_name: str = "treatment", **row_kwargs
) -> dict:
    captures = tmp_path / "captures"
    captures.mkdir(parents=True)
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", ROUND1)
    if round2 is not None:
        _capture(captures, "with_nexus", round2)
    rows = _rows(tmp_path / "archive", **row_kwargs)
    return audit_run(captures, _material(), rows=rows, run_id="r1", lane=lane_name)


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
    strict = load_block_schema("strict")
    treatment = load_block_schema("treatment")
    changed = {
        (header, path)
        for header, paths in strict.items()
        for path, spec in paths.items()
        if treatment[header][path] != spec
    }
    assert changed == {
        ("[NEXUS EXECUTOR FLAGS]", "ddtree_max_candidates"),
        ("[NEXUS ROUTE SUMMARY]", "recommended_flow"),
        ("[NEXUS EXECUTION PROFILE]", "candidate_count"),
        ("[NEXUS EXECUTION PROFILE]", "max_rounds"),
    }


@pytest.mark.parametrize(
    "round2, violation",
    [
        # a hidden-only literal that is not the model's own text
        (
            _round2(extra="Note: unverified evidence maps to needs_evidence.\n"),
            "hidden_literal_in_with_nexus_prompt",
        ),
        # a hidden test line
        (
            _round2(extra="    assert classify(True, {'verified': False}) == 'needs_evidence'\n"),
            "hidden_test_line_in_with_nexus_prompt",
        ),
        # a task hint the bare arm never sees
        (
            _round2(extra="Hint: return open unless the evidence is verified.\n"),
            "treatment_round_not_allowed",
        ),
        # failure text the runner's own visible run never printed
        (
            _round2(failure="E   expected the canonical needs_evidence status\n"),
            "treatment_round_not_allowed",
        ),
        # the local support candidate block
        (
            _round2(extra="[NEXUS LOCAL SUPPORT CANDIDATE]\nreturn 'resolved'\n"),
            "treatment_round_not_allowed",
        ),
        # a "candidate" that is not one of the row's archived model candidates
        (
            _round2(
                candidate="def classify(smoke_passed, semantic_evidence):\n    return smoke_passed and 'resolved'\n"
            ),
            "treatment_round_not_allowed",
        ),
    ],
    ids=[
        "hidden_literal",
        "hidden_line",
        "hint",
        "failure_not_in_visible_output",
        "local_support",
        "non_model_candidate",
    ],
)
def test_treatment_round_two_fails_closed(tmp_path: Path, round2: str, violation: str) -> None:
    report = _audit(tmp_path, round2)
    assert report["status"] == "FAIL"
    assert violation in report["tasks"][0]["violations"], report["tasks"][0]


def test_captured_calls_must_equal_row_model_calls_and_the_cap(tmp_path: Path) -> None:
    mismatch = _audit(tmp_path, _round2(), model_calls=3)
    assert any(
        v.startswith("with_nexus_calls_mismatch") for v in mismatch["tasks"][0]["violations"]
    )
    over = _audit(tmp_path / "o", _round2(), max_calls=1)
    assert "with_nexus_calls=2>treatment_max=1" in over["tasks"][0]["violations"]


def test_bare_arm_stays_at_one_call_in_the_treatment_lane(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "without_nexus", BARE + "\nretry\n")
    _capture(captures, "with_nexus", ROUND1)
    report = audit_run(
        captures,
        _material(),
        rows=_rows(tmp_path / "a", model_calls=1),
        run_id="r1",
        lane="treatment",
    )
    assert "bare_calls=2" in report["tasks"][0]["violations"]


def test_tampered_candidate_archive_fails_the_round_audit(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", ROUND1)
    _capture(captures, "with_nexus", _round2())
    rows = _rows(tmp_path / "archive")
    (tmp_path / "archive" / f"{_sha(CANDIDATE1)}.txt").write_text(
        CANDIDATE1 + "# edited\n", encoding="utf-8"
    )
    report = audit_run(captures, _material(), rows=rows, run_id="r1", lane="treatment")
    assert report["status"] == "FAIL"
    assert any(
        "candidate_archive_sha_mismatch" in f
        for f in report["tasks"][0]["treatment_round_findings"]
    )


def test_runner_rescue_is_a_row_violation_in_the_treatment_lane(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    captures.mkdir()
    _capture(captures, "without_nexus", BARE)
    _capture(captures, "with_nexus", ROUND1)
    rows = _rows(tmp_path / "a", model_calls=1)
    rows[1]["bounded_nexus_rescue_used"] = True
    report = audit_run(captures, _material(), rows=rows, run_id="r1", lane="treatment")
    assert any("runner_rescue_in_treatment_lane" in v for v in report["row_violations"])


def test_output_line_normalisation_drops_only_volatile_parts() -> None:
    assert (
        normalize_output_line("/tmp/a/b/test_visible.py:2: AssertionError")
        == "test_visible.py:2: AssertionError"
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
    _capture(captures, "with_nexus", _round2(extra="Hint: needs_evidence when unverified.\n"))
    rows = _rows(tmp_path / "a")
    for row in rows:
        row.update({"status": "SUCCESS", "hidden_verifier_passed": True})
    rows[1].update({
        "first_attempt_hidden_passed": True,
        "first_model_candidate_sha256": rows[1]["model_candidate_sha256s"][0],
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
        "first_model_candidate_sha256": a,
        "final_model_candidate_sha256": b,
        "final_candidate_in_model_candidates": True,
        "first_attempt_hidden_passed": False,
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
        first_attempt_hidden_passed=True,
    )
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == MODEL_SOLVE
    assert row["first_attempt"] is True and row["after_treatment"] is True


def test_delivered_candidate_outside_the_model_candidates_never_counts() -> None:
    row = _treated_row(
        final_candidate_in_model_candidates=False,
        model_candidate_sha256=_sha("local"),
        final_model_candidate_sha256=_sha("local"),
    )
    apply_strict_llm_baseline_classification([row])
    assert row["solve_classification"] == NOT_SOLVED and row["treatment_sha_unbound"] is True
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
    solved_first = _treated_row(
        task_id="u",
        model_calls=1,
        total_tokens=120,
        nexus_winner_source="llm",
        model_candidate_sha256=_sha("a"),
        final_model_candidate_sha256=_sha("a"),
        model_candidate_sha256s=[_sha("a")],
        model_candidate_sources=["llm"],
        first_attempt_hidden_passed=True,
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


def test_treatment_applied_comes_from_attested_evidence_only() -> None:
    row = _treated_row(
        capability_receipts=[
            {
                "name": "ultra_review",
                "selected": True,
                "invoked": True,
                "attestation": "real_self_reported",
                "evidence_refs": ["x"],
            },
            {"name": "sandbox", "selected": True, "invoked": False},
        ],
        treatment_applied=["claimed_by_product"],
    )
    lane.attest_row(row, {"with_nexus_calls": 2, "self_heal_rounds_observed": 1})
    assert row["treatment_applied"] == ["self_heal"]
    assert row["treatment_calls_reconciled"] is True
    unreconciled = _treated_row()
    lane.attest_row(unreconciled, {"with_nexus_calls": 1, "self_heal_rounds_observed": 1})
    assert unreconciled["treatment_applied"] == []


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


def _with_nexus_row(
    tmp_path: Path, monkeypatch, *, lane_name: str, candidates: list[str]
) -> tuple[dict, list[dict]]:
    """run_with_nexus with a fake product subprocess (zero model calls) and the REAL hidden test."""

    from scripts.bench.capability_ab_runner import _materialize_fixture, load_tasks, run_with_nexus
    from scripts.bench.capability_ab_runner import _run_process_group as real_run_process_group

    monkeypatch.setenv("NEXUS_BENCH_NO_TASK_HINTS", "1")
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.setenv("NEXUS_BENCH_LANE", lane_name)
    monkeypatch.setenv("NEXUS_BENCH_TREATMENT_MAX_MODEL_CALLS", "4")
    tasks = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")
    task = next(t for t in tasks if t.id == "nexus-value-trust-002")
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    envs: list[dict] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            envs.append(dict(env))
            treatment = env.get("NEXUS_BENCH_TREATMENT_LANE") == "1"
            produced = candidates if treatment else candidates[:1]
            archive = env.get("NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR", "")
            trace: dict = {}
            for index, code in enumerate(produced):
                if archive:
                    os.environ["NEXUS_BENCH_CANDIDATE_ARCHIVE_DIR"] = archive
                product_lane.record_model_candidate(
                    trace, code, "llm" if index == 0 else "llm_self_heal"
                )
            final = produced[-1]
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
                        "winner_source": "llm" if len(produced) == 1 else "llm_self_heal",
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
    return row, envs


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
    assert treated_row["final_model_candidate_sha256"] == _sha(candidates[-1])
    assert treated_row["model_calls"] == len(candidates) and treated_row["tokens"] == 100 * len(
        candidates
    )
    assert treated_row["treatment_rounds"] == len(candidates)
    expected_status = "verified_as_delivered" if len(candidates) == 1 else "verified_from_archive"
    assert treated_row["first_attempt_status"] == expected_status
    # the bare arm is identical in both lanes (one call)
    for bare in (strict_bare, treated_bare):
        assert bare["first_attempt"] is strict_solved and bare["after_treatment"] is strict_solved
    assert treated_bare["lane"] == "treatment" and treated_bare["bare_retries"] == 0
    if len(candidates) > 1:
        assert set(treated_row["treatment_visible_outputs"]) == {_sha(candidates[0])}


def test_first_attempt_reverification_restores_the_delivered_file(
    tmp_path: Path, monkeypatch
) -> None:
    row, _ = _with_nexus_row(
        tmp_path, monkeypatch, lane_name="treatment", candidates=[BAD_CLASSIFY, GOOD_CLASSIFY]
    )
    target = next(tmp_path.rglob("*.py"), None)
    assert target is not None
    delivered = [
        p for p in tmp_path.rglob("*.py") if p.read_text(encoding="utf-8") == GOOD_CLASSIFY
    ]
    assert delivered, "the final (delivered) candidate must be back in the target file"
    assert row["first_attempt_hidden_passed"] is False and row["hidden_verifier_passed"] is True


def test_unarchived_first_candidate_is_not_verifiable_and_never_counts(tmp_path: Path) -> None:
    os.environ["NEXUS_BENCH_LANE"] = "treatment"
    target = tmp_path / "t.py"
    target.write_text("x = 2\n", encoding="utf-8")
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

    def never(_timeout):
        raise AssertionError("no verifier may run on a candidate that is not archived")

    lane.finalize_with_nexus_row(
        row,
        payload,
        target_file=str(target),
        verification_test_file=str(tmp_path / "test_hidden.py"),
        archive_dir=str(tmp_path / "empty"),
        run_hidden=never,
        run_visible=never,
        timeout_sec=10,
    )
    assert row["first_attempt_status"] == "first_candidate_unarchived"
    assert row["first_attempt_hidden_passed"] is None
    row.update({
        "mode": "with_nexus",
        "status": "SUCCESS",
        "model_calls": 2,
        "nexus_winner_source": "llm_self_heal",
    })
    apply_strict_llm_baseline_classification([row])
    assert row["first_attempt"] is False


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
