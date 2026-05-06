from __future__ import annotations

from scripts.ops import codex_nexus_ab_smoke


def test_build_command_locks_codex_bare_and_nexus_arms():
    cmd = codex_nexus_ab_smoke.build_command(
        output_dir=".nexus/reports/test",
        task_ids=("a", "b"),
        preflight_only=True,
    )

    assert cmd[1] == "scripts/bench/capability_ab_runner.py"
    assert cmd[cmd.index("--with-model-provider") + 1] == "codex"
    assert cmd[cmd.index("--without-mode") + 1] == "codex"
    assert cmd[cmd.index("--with-llm-mode") + 1] == "all"
    assert cmd[cmd.index("--task-id-filter") + 1] == "a,b"
    assert "--enable-autoreason-executor" in cmd
    assert "--enable-ddtree-executor" in cmd
    assert "--enable-ultra-review-dry-gate" in cmd
    assert cmd[cmd.index("--llm-candidate-cap") + 1] == "3"
    assert "--preflight-only" in cmd


def test_benchmark_env_locks_same_model(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "existing")

    env = codex_nexus_ab_smoke.benchmark_env("gpt-5.5")

    assert env["NEXUS_VALUE_HIDDEN_VERIFIER"] == "1"
    assert env["NEXUS_CODEX_MODEL_NAME"] == "gpt-5.5"
    assert env["NEXUS_DIRECT_CODEX_MODEL"] == "gpt-5.5"
    assert "existing" in env["PYTHONPATH"]


def test_validate_smoke_plan_requires_preflight_and_receipt_flags():
    task_ids = ("a", "b")
    cmd = codex_nexus_ab_smoke.build_command(
        output_dir=".nexus/reports/test",
        task_ids=task_ids,
        preflight_only=True,
    )
    env = codex_nexus_ab_smoke.benchmark_env("gpt-5.5")

    payload = codex_nexus_ab_smoke.validate_smoke_plan(cmd=cmd, env=env, task_ids=task_ids)

    assert payload["passed"] is True
    assert payload["same_model"] is True
    assert payload["preflight_only"] is True
    assert payload["reason_codes"] == []


def test_validate_smoke_plan_fails_closed_on_model_or_task_drift():
    task_ids = ("a", "b")
    cmd = codex_nexus_ab_smoke.build_command(
        output_dir=".nexus/reports/test",
        task_ids=("a",),
        preflight_only=False,
    )
    env = codex_nexus_ab_smoke.benchmark_env("gpt-5.5")
    env["NEXUS_DIRECT_CODEX_MODEL"] = "other-model"

    payload = codex_nexus_ab_smoke.validate_smoke_plan(cmd=cmd, env=env, task_ids=task_ids)

    assert payload["passed"] is False
    assert "same_model_lock_missing" in payload["reason_codes"]
    assert "task_id_filter_mismatch" in payload["reason_codes"]
    assert "preflight_guard_missing" in payload["reason_codes"]
