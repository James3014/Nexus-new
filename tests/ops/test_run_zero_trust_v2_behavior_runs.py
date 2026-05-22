from __future__ import annotations

import json
import subprocess

from scripts.ops.run_zero_trust_v2_behavior_runs import build_zero_trust_v2_behavior_run_hook
from scripts.ops.run_zero_trust_v2_behavior_runs import _export_runtime_signed_receipt
from scripts.ops.run_zero_trust_v2_behavior_runs import _matrix_run_plan
from scripts.ops.run_zero_trust_v2_behavior_runs import _bundle_has_runtime_receipt_export_pass
from nexus.learning.zero_trust_v2_receipts import verify_runtime_signed_receipt


def _run(env: dict) -> dict:
    return {
        "m29_three_run_plan": [
            {
                "run_index": 1,
                "run_id": "run-01",
                "command": ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"],
                "runner_env": env,
                "expected_evidence_bundle": ".nexus/reports/run-01/evidence_bundle.json",
            }
        ]
    }


def test_behavior_run_hook_requires_bound_runner_env() -> None:
    result = build_zero_trust_v2_behavior_run_hook(plan=_run({}), execute=False)

    assert result["status"] == "BLOCKED"
    assert "missing_or_invalid_env:NEXUS_VALUE_HIDDEN_VERIFIER" in result["blockers"]
    assert result["summary"]["promotion_credit_allowed"] is False


def test_behavior_run_hook_accepts_safe_dry_run_env() -> None:
    result = build_zero_trust_v2_behavior_run_hook(
        plan=_run(
            {
                "NEXUS_ZERO_TRUST_V2_PHYSICAL_BEHAVIOR": "1",
                "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
                "NEXUS_BENCH_SKILL_MOUNTS": "1",
                "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
                "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": "[\"browse\"]",
            }
        ),
        execute=False,
    )

    assert result["status"] == "PASS"
    assert result["summary"]["ready_count"] == 1
    assert result["runs"][0]["status"] == "READY"


def test_runtime_signed_receipt_export_stamps_clean_bundle(tmp_path, monkeypatch) -> None:
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "row_counts": {"eligible_with_nexus": 1, "infra_invalid_with_nexus": 0},
                "raw_files": {"with_nexus": {"sha256": "artifact-hash"}},
                "rubric_contract": {"with_nexus": {"hard_fail_reasons": []}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")

    result = _export_runtime_signed_receipt(
        bundle_path=str(bundle),
        run_id="run-1",
        capability_id="policy_capability_gate",
        skill_id="browse",
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    receipt = payload["zero_trust_v2_runtime_receipt"]
    assert result["status"] == "PASS"
    assert result["signing_secret_source"] == "env"
    assert verify_runtime_signed_receipt(receipt, secret="test-secret") is True
    assert "test-secret" not in str(payload)


def test_matrix_run_plan_expands_ready_adapters_to_three_runs() -> None:
    result = _matrix_run_plan(
        {
            "adapters": [
                {
                    "capability_id": "policy_capability_gate",
                    "skill_id": "browse",
                    "priority": "P0",
                    "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN",
                    "command": ["uv", "run", "--output-dir", ".nexus/reports/zero_trust_v2_behavior"],
                    "runner_env": {"NEXUS_VALUE_HIDDEN_VERIFIER": "1"},
                },
                {"capability_id": "codeintel", "priority": "P1", "status": "BLOCKED"},
            ]
        }
    )

    rows = result["m29_three_run_plan"]
    assert len(rows) == 3
    assert rows[0]["capability_id"] == "policy_capability_gate"
    assert rows[0]["skill_id"] == "browse"
    assert rows[0]["expected_evidence_bundle"].endswith(
        "policy_capability_gate/browse/run-01/evidence_bundle.json"
    )
    assert rows[0]["command"][rows[0]["command"].index("--output-dir") + 1].endswith(
        "policy_capability_gate/browse/run-01"
    )

    hook = build_zero_trust_v2_behavior_run_hook(plan=result, execute=False, run_index=1)
    assert hook["runs"][0]["capability_id"] == "policy_capability_gate"
    assert hook["runs"][0]["skill_id"] == "browse"


def test_behavior_run_hook_blocks_when_execution_fails(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr("scripts.ops.run_zero_trust_v2_behavior_runs.subprocess.run", fake_run)
    result = build_zero_trust_v2_behavior_run_hook(
        plan=_run(
            {
                "NEXUS_ZERO_TRUST_V2_PHYSICAL_BEHAVIOR": "1",
                "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
                "NEXUS_BENCH_SKILL_MOUNTS": "1",
                "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
                "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": "[\"browse\"]",
            }
        ),
        execute=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["runs"][0]["status"] == "EXECUTION_FAILED"
    assert "execution_failed:2" in result["blockers"]


def test_matrix_run_plan_missing_only_skips_existing_clean_bundle(tmp_path, monkeypatch) -> None:
    bundle = tmp_path / ".nexus" / "reports" / "zero_trust_v2_behavior" / "memory" / "skill-a" / "run-01" / "evidence_bundle.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text(json.dumps({"zero_trust_v2_runtime_receipt_export": {"status": "PASS"}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _matrix_run_plan(
        {
            "adapters": [
                {
                    "capability_id": "memory",
                    "skill_id": "skill-a",
                    "priority": "P2",
                    "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN",
                    "command": ["uv", "run", "--output-dir", ".nexus/reports/zero_trust_v2_behavior"],
                    "runner_env": {"NEXUS_VALUE_HIDDEN_VERIFIER": "1"},
                },
                {
                    "capability_id": "nightshift",
                    "skill_id": "skill-b",
                    "priority": "P2",
                    "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN",
                    "command": ["uv", "run", "--output-dir", ".nexus/reports/zero_trust_v2_behavior"],
                    "runner_env": {"NEXUS_VALUE_HIDDEN_VERIFIER": "1"},
                },
            ]
        },
        run_index=1,
        missing_only=True,
    )

    assert _bundle_has_runtime_receipt_export_pass(str(bundle)) is True
    rows = result["m29_three_run_plan"]
    assert len(rows) == 1
    assert rows[0]["capability_id"] == "nightshift"
