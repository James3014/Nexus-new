"""Armor axis for the memory A/B runner (issue #1821). A fake executor stands in for the model.

The armor-on test runs the real CapabilityPlanner, run_mainchain and LocalAssistService; only the
LocalModelExecutor call is faked, so the receipt fields asserted here come from the runtime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import run_memory_ab_v1 as runner  # noqa: E402

ADMITTED_MODEL = (
    "qwen2.5-coder:7b-instruct"  # the model Workforce Admission pins for local_coder_7b
)
BUGGY = "def f():\n    return 1\n"
FIXED = "def f():\n    return 2\n"
REPRO = "import sys\nfrom m import f\nsys.exit(0 if f() == 2 else 1)\n"
PATCH = "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
LEGACY_ROW_KEYS = {
    "task_fingerprint", "task_id", "attempt_id", "attempt_index", "action_id", "source_revision",
    "source_tree", "verifier_status", "verifier_artifact", "verifier_artifact_hash",
    "verifier_receipt", "memory_arm", "retrieved_lesson_ids", "applied_attributed_lesson_ids",
    "applied_lesson_ids", "evidence_origin", "evidence_refs", "terminal_outcome",
    "measured_elapsed_seconds", "intervention_events", "intervention_count",
    "forbidden_strategy_identity", "forbidden_strategy_violation_event", "missingness_reasons",
    "ineligibility_reasons", "workflow", "workflow_revision", "nexus_memory_arm", "memory_enabled",
    "memory_flag_applied", "model", "run_id", "solve_eligible", "receipt_path", "pipeline_status",
    "failure_reason", "repro_returncode", "wall_duration_sec", "model_calls",
    "model_call_failures", "episode_found", "prompt_sha256", "work_dir",
}  # fmt: skip


def make_tasks(root: Path) -> Path:
    task_dir = root / "tasks" / "toy-0"
    task_dir.mkdir(parents=True)
    (task_dir / "m.py").write_text(BUGGY, encoding="utf-8")
    (task_dir / "repro.py").write_text(REPRO, encoding="utf-8")
    (task_dir / "task.json").write_text(
        json.dumps({
            "id": "toy-0",
            "bug_class": "toy",
            "variant": "0",
            "problem_statement": "f() returns 1 instead of 2",
            "target_file": "m.py",
            "repro_file": "repro.py",
        }),
        encoding="utf-8",
    )
    return root / "tasks"


def fake_pipeline(ctx, generate_fn):
    """Bare local heal: no capabilities beyond the single local_heal_repair stage, receipt on disk."""
    for key, value in ctx.route_context["semantic_retry_seed"].items():
        setattr(ctx, key, value)
    (ctx.repo_dir / "m.py").write_text(FIXED, encoding="utf-8")
    ctx.solve_eligible = True
    receipt = ctx.repo_dir.parent / f"{ctx.instance_id}-receipt.json"
    receipt.write_text(
        json.dumps({
            "p4_committee_invoked": False,
            "receipt_base": {
                "with_nexus_armor": False,
                "consumption_chain": [
                    {
                        "capability": "local_heal_repair",
                        "selected": True,
                        "used": True,
                        "evidence_present": True,
                    }
                ],
            },
        }),
        encoding="utf-8",
    )
    ctx.receipt_path = str(receipt)
    return ctx


def fake_executor_factory(profile: str):
    from nexus.services.local_heal.local_model_executor import LocalModelExecutorResponse

    def run(request, *, provider=None):
        selected = list(request.selected_capabilities)
        meta = {
            "selected_capabilities": selected,
            "selected_capabilities_used": ["local_model_executor"],
            "capability_usage_status": {"local_model_executor": "used"},
            "localheal_pipeline_run_called": True,
            "final_execution_profile": profile,
            "initial_execution_profile": profile,
            # Advisory stubs: invoked=True with an empty candidate pool. Must not count.
            "ddtree_result": {"invoked": True, "telemetries": {"candidate_count": 0}},
            "autoreason_result": {"invoked": True, "telemetries": {}},
            "p4_committee_invoked": False,
            "llm_call_ledger_records": [{"prompt_hash": "p" * 16, "duration_sec": 0.01}],
        }
        return LocalModelExecutorResponse(
            invoked=True,
            local_model_called=True,
            candidate_patch=PATCH,
            candidate_hash="",
            reasoning_summary="fake",
            raw_model_metadata=meta,
            provider="ollama",
            model_name="fake-model",
            error="",
            timeout=False,
            evidence_refs=tuple(request.evidence_refs),
        )

    return run


@pytest.fixture
def harness(tmp_path, monkeypatch):
    watched = tmp_path / "watched"
    watched.mkdir()
    monkeypatch.setattr(runner, "preflight_model", lambda *a, **k: None)
    monkeypatch.setattr(runner, "redirect_learning_state", lambda root, reports=None: None)
    monkeypatch.setattr(runner, "STATE_WATCH_ROOTS", [watched])
    monkeypatch.setattr(runner, "git_head", lambda repo: "0" * 40)
    monkeypatch.setattr(runner, "git_tree_head", lambda repo: "1" * 40)
    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")
    for key in (
        "NEXUS_OLLAMA_MODEL",
        "NEXUS_PATCH_TIMEOUT_SECONDS",
        "NEXUS_LEARNING_REFLECT_JUDGE",
        "NEXUS_LEARNING_STATE_ROOT",
    ):
        monkeypatch.setenv(key, "")
    return {"root": tmp_path, "monkeypatch": monkeypatch}


def use_fake_executor(harness, profile: str = "FULL") -> None:
    real_build = runner.build_armor_service

    def build_service(apply_parent: Path, executor_sink: dict, executor_runner=None):
        return real_build(apply_parent, executor_sink, fake_executor_factory(profile))

    harness["monkeypatch"].setattr(runner, "build_armor_service", build_service)


def run_main(harness, run_id: str, extra: list[str], arms: str = "off,on") -> list[dict]:
    args = [
        "--tasks-dir", str(make_tasks(harness["root"]) if not (harness["root"] / "tasks").exists() else harness["root"] / "tasks"),
        "--run-id", run_id,
        "--artifact-root", str(harness["root"] / "art"),
        "--arms", arms,
        "--model", ADMITTED_MODEL,
        *extra,
    ]  # fmt: skip
    assert runner.main(args) == 0
    run_root = harness["root"] / "art" / run_id
    return [json.loads(line) for line in (run_root / "rows.jsonl").read_text().splitlines()]


def test_armor_off_rows_keep_legacy_schema_and_report_bare_receipt(harness):
    rows = run_main(harness, "off1", [])
    assert len(rows) == 2
    for row in rows:
        assert LEGACY_ROW_KEYS <= set(row)
        assert set(row) - LEGACY_ROW_KEYS == set(runner.ARMOR_ROW_KEYS) | {"armor_evidence"}
        assert row["armor"] == "off"
        assert row["armor_profile"] == "none"
        assert row["with_nexus_armor"] is False
        assert row["committee_invoked"] is False
        assert row["capabilities_selected"] == ["local_heal_repair"]
        assert row["capabilities_invoked"] == ["local_heal_repair"]
        assert row["armor_evidence"]["evidence_source"] == "local_heal_receipt"
        assert row["terminal_outcome"] == "SUCCEEDED"
    card = json.loads((harness["root"] / "art" / "off1" / "scorecard.json").read_text())
    assert card["armor_axis"]["armor"] == "off"
    assert card["armor_axis"]["attempts_with_nexus_armor"] == 0
    assert all(set(runner.ARMOR_ROW_KEYS) <= set(a) for a in card["armor_axis"]["attempts"])


@pytest.mark.parametrize("profile", ["FULL", "STANDARD"])
def test_armor_on_rows_prove_planner_capabilities_from_receipt(harness, profile):
    use_fake_executor(harness, profile)
    rows = run_main(harness, f"on-{profile}", ["--armor", "on", "--armor-profile", profile])
    assert len(rows) == 2
    off_arm, on_arm = rows
    for row in rows:
        assert row["armor"] == "on"
        assert row["armor_profile"] == profile
        assert row["with_nexus_armor"] is True
        assert row["ineligibility_reasons"] == []
        assert row["capabilities_selected"], "planner selected nothing"
        assert row["capabilities_invoked"], "no capability left invocation evidence"
        assert "local_model_executor" in row["capabilities_invoked"]
        assert set(row["capabilities_invoked"]) - {"committee"} <= set(
            row["capabilities_selected"]
        ) | {"local_model_executor", "repair_loop", "memory"}
        # Advisory stubs (empty-pool ddtree/autoreason) are reported but never counted.
        assert "ddtree" not in row["capabilities_invoked"]
        assert "autoreason" not in row["capabilities_invoked"]
        assert row["armor_evidence"]["advisory_stub_capabilities"] == ["autoreason", "ddtree"]
        assert row["armor_evidence"]["armor_profile_observed"] == profile
        assert row["armor_evidence"]["candidate_materialized"] == "applied"
        assert row["committee_invoked"] is False
        assert row["model_calls"] == 1
        assert row["terminal_outcome"] == "SUCCEEDED"  # decided by the independent repro rerun
    # Memory arm is orthogonal: the off arm never queries memory or lists it for the executor.
    assert "memory" not in off_arm["armor_evidence"]["local_selected_capabilities"]
    assert off_arm["armor_evidence"]["memory_probe"] == "memory_arm_off"
    assert off_arm["armor_evidence"]["memory_signal_hits"] == 0
    assert on_arm["armor_evidence"]["memory_probe"] != "memory_arm_off"
    assert off_arm["memory_flag_applied"] and on_arm["memory_flag_applied"]
    card = json.loads((harness["root"] / "art" / f"on-{profile}" / "scorecard.json").read_text())
    axis = card["armor_axis"]
    assert axis["armor_profile"] == profile
    assert axis["attempts_with_nexus_armor"] == 2
    assert "local_model_executor" in axis["capabilities_invoked_union"]
    validation = json.loads(
        (harness["root"] / "art" / f"on-{profile}" / "validation.json").read_text()
    )
    assert validation["with_nexus_armor_verified"] is True


def test_with_nexus_armor_true_only_when_armor_on(harness):
    use_fake_executor(harness)
    off_rows = run_main(harness, "cmp-off", [], arms="off")
    on_rows = run_main(harness, "cmp-on", ["--armor", "on"], arms="off")
    assert [r["with_nexus_armor"] for r in off_rows] == [False]
    assert [r["with_nexus_armor"] for r in on_rows] == [True]
    assert off_rows[0]["capabilities_invoked"] == ["local_heal_repair"]
    assert on_rows[0]["capabilities_invoked"] != ["local_heal_repair"]


def test_armor_on_rejects_model_without_admitted_worker(harness, capsys):
    args = [
        "--tasks-dir", str(make_tasks(harness["root"])),
        "--run-id", "bad-model",
        "--artifact-root", str(harness["root"] / "art"),
        "--model", "incoai/Qwen3.6-35B-A3B-Splash",
        "--armor", "on",
    ]  # fmt: skip
    assert runner.main(args) == runner.EXIT_PREFLIGHT
    assert "workforce-admitted local worker" in capsys.readouterr().err
    assert not (harness["root"] / "art" / "bad-model" / "rows.jsonl").exists()


def test_armor_profile_requires_armor_on():
    with pytest.raises(SystemExit):
        runner.parse_args(["--armor-profile", "FULL"])
    assert runner.parse_args([]).armor == "off"
    assert runner.parse_args(["--armor", "on"]).armor_profile == "FULL"


def test_profile_mismatch_is_an_ineligibility_reason(harness):
    use_fake_executor(harness, profile="FULL")  # executor resolves FULL although STANDARD requested
    rows = run_main(
        harness, "mismatch", ["--armor", "on", "--armor-profile", "STANDARD"], arms="off"
    )
    assert "armor_profile_not_applied" in rows[0]["ineligibility_reasons"]


def test_stub_only_capabilities_are_not_invoked():
    receipt = {
        "selected_capabilities": ["codeintel", "research_route"],
        "capabilities": [
            {
                "name": "research_route",
                "status": "SKIPPED",
                "invoked": False,
                "skipped": True,
                "evidence_present": True,
                "physical_callable": "capability_registry.explicit_skip:research_route",
            },
            {
                "name": "codeintel",
                "status": "INVOKED",
                "invoked": True,
                "skipped": False,
                "evidence_present": True,
                "physical_callable": "capability_executor_registry:codeintel",
            },
        ],
        "receipt_base": {"with_nexus_armor": True},
    }
    evidence = runner.extract_armor_evidence(receipt)
    assert evidence["capabilities_invoked"] == ["codeintel"]
    assert evidence["with_nexus_armor"] is True
    assert evidence["committee_invoked"] is False


def test_heal_receipt_stage_that_ran_counts_even_when_it_did_not_solve(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps({
            "p4_committee_invoked": False,
            "receipt_base": {
                "with_nexus_armor": False,
                "consumption_chain": [
                    {
                        "capability": "local_heal_repair",
                        "selected": True,
                        "used": False,
                        "evidence_present": True,
                    }
                ],
            },
        }),
        encoding="utf-8",
    )
    evidence = runner.extract_heal_receipt_evidence(str(path))
    assert evidence["capabilities_invoked"] == ["local_heal_repair"]
    assert runner.extract_heal_receipt_evidence(str(tmp_path / "nope.json"))["evidence_source"] == (
        "missing"
    )
