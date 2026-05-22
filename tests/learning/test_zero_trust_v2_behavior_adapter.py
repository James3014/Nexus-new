from __future__ import annotations

import json

from nexus.learning.zero_trust_v2_behavior_adapter import (
    build_behavior_runner_adapter,
    build_behavior_runner_env,
    validate_behavior_runner_env,
)


def test_behavior_adapter_blocks_without_fresh_task_ref() -> None:
    adapter = build_behavior_runner_adapter(
        {
            "capability_id": "codeintel",
            "skill_id": "code-skill",
            "priority": "P0",
        }
    )

    assert adapter["status"] == "BLOCKED"
    assert adapter["command"] == []
    assert "MISSING_FRESH_TASK_REF_FOR_V2_PHYSICAL_RUN" in adapter["failed_security_contract_rules"]
    assert adapter["promotion_credit_allowed"] is False


def test_behavior_adapter_builds_safe_capability_runner_command(tmp_path) -> None:
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps([{"id": "task-1"}]), encoding="utf-8")

    adapter = build_behavior_runner_adapter(
        {
            "capability_id": "codeintel",
            "skill_id": "code-skill",
            "priority": "P0",
            "task_ref": {"manifest": str(manifest), "task_id": "task-1"},
        }
    )

    assert adapter["status"] == "READY_FOR_PHYSICAL_BEHAVIOR_RUN"
    assert adapter["command"][:4] == ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"]
    assert "--task-id-filter" in adapter["command"]
    assert adapter["model_provider"] == "codex"
    assert adapter["model_name"] == "gpt-5.5"
    assert "--with-model-provider" in adapter["command"]
    assert adapter["command"][adapter["command"].index("--with-model-provider") + 1] == "codex"
    assert "--gemini-model" not in adapter["command"]
    assert "--model" not in adapter["command"]
    assert "--evidence-bundle" in adapter["command"]
    assert "--neutralize-history" in adapter["command"]
    assert "--disable-learning-loop" in adapter["command"]
    assert adapter["runner_env"]["NEXUS_VALUE_HIDDEN_VERIFIER"] == "1"
    assert adapter["runner_env"]["NEXUS_CODEX_MODEL_NAME"] == "gpt-5.5"
    assert json.loads(adapter["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == ["code-skill"]


def test_behavior_adapter_keeps_gemini_as_explicit_replay_provider(tmp_path) -> None:
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps([{"id": "task-1"}]), encoding="utf-8")

    adapter = build_behavior_runner_adapter(
        {
            "capability_id": "codeintel",
            "skill_id": "code-skill",
            "priority": "P0",
            "task_ref": {"manifest": str(manifest), "task_id": "task-1"},
        },
        provider="gemini",
        model="gemini-3-flash",
    )

    assert adapter["model_provider"] == "gemini"
    assert "--gemini-model" in adapter["command"]
    assert adapter["command"][adapter["command"].index("--gemini-model") + 1] == "gemini-3-flash"
    assert adapter["command"][adapter["command"].index("--with-model-provider") + 1] == "gemini"
    assert adapter["runner_env"]["NEXUS_GEMINI_MODEL_NAME"] == "gemini-3-flash"


def test_behavior_runner_env_rejects_secret_like_keys() -> None:
    env = build_behavior_runner_env(skill_id="code-skill")
    env["NEXUS_SYSTEM_SALT"] = "leak"

    result = validate_behavior_runner_env(env)

    assert result["status"] == "BLOCKED"
    assert "RUNNER_ENV_SECRET_KEY:NEXUS_SYSTEM_SALT" in result["failed_security_contract_rules"]
