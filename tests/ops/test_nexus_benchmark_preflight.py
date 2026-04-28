from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.nexus_benchmark_preflight import build_preflight_report, main


def _write_repo(root: Path) -> str:
    package = root / "nexus" / "app"
    package.mkdir(parents=True)
    (root / "nexus" / "__init__.py").write_text("", encoding="utf-8")
    (root / "nexus" / "app" / "__init__.py").write_text("", encoding="utf-8")
    target = package / "research_flow_service.py"
    target.write_text(
        "from nexus.app.helper import normalize\n\n"
        "def run(value):\n"
        "    return normalize(value)\n",
        encoding="utf-8",
    )
    (package / "helper.py").write_text(
        "def normalize(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    return "nexus/app/research_flow_service.py"


def test_build_preflight_report_passes_without_gemini(tmp_path, monkeypatch):
    changed_file = _write_repo(tmp_path)
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")

    report = build_preflight_report(tmp_path, changed_file=changed_file)

    assert report["schema"] == "nexus_benchmark_preflight_readiness_v1"
    assert report["ready_for_benchmark"] is True
    assert report["ready_for_smoke"] is True
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["codeintel_evidence"]["passed"] is True
    assert checks["codeintel_evidence"]["evidence"]["schema_version"] == "codeintel-v1"
    assert checks["rlm_trace_quality"]["evidence"]["rlm_trace_quality_score"] >= 60
    assert checks["jit_promotion_boundary"]["evidence"]["default_switch_allowed"] is False
    assert checks["public_claim_gate"]["evidence"]["fail_gate"]["verdict"] == "FAIL"
    assert checks["memory_bootstrap_fail_open"]["passed"] is True
    assert checks["memory_bootstrap_fail_open"]["evidence"]["auto_init"] == "0"
    contracts = {item["id"]: item for item in report["benchmark_contract_matrix"]}
    assert list(contracts) == [f"P{index}" for index in range(1, 14)]
    assert contracts["P2"]["status"] == "deferred_smoke"
    assert contracts["P3"]["evidence"]["manifest_sha256"]
    assert contracts["P3"]["evidence"]["hidden_verifier_enabled"] is True
    assert contracts["P4"]["evidence"]["same_model"] is True
    assert contracts["P5"]["evidence"]["required_fields"] == [
        "model_calls",
        "gemini_uses_nexus",
        "nexus_context_delivered",
        "nexus_usage_valid",
        "capability_claim_verified",
    ]
    assert contracts["P12"]["evidence"]["per_task_stop_loss_sec"] == 600
    assert contracts["P13"]["evidence"]["token_policy"] == "measured_required_for_cost_claim"


def test_build_preflight_report_fails_when_changed_file_is_missing(tmp_path):
    report = build_preflight_report(tmp_path, changed_file="missing.py")

    assert report["ready_for_benchmark"] is False
    assert report["ready_for_smoke"] is False
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["codeintel_evidence"]["passed"] is False
    assert checks["codeintel_evidence"]["reason"] == "changed_file_missing"


def test_build_preflight_report_blocks_unsafe_timeout_policy(tmp_path):
    changed_file = _write_repo(tmp_path)

    report = build_preflight_report(tmp_path, changed_file=changed_file, per_task_stop_loss_sec=900)

    assert report["ready_for_benchmark"] is False
    contracts = {item["id"]: item for item in report["benchmark_contract_matrix"]}
    assert contracts["P12"]["status"] == "blocked"
    assert contracts["P12"]["evidence"]["per_task_stop_loss_sec"] == 900


def test_build_preflight_report_blocks_when_hidden_verifier_is_required(tmp_path, monkeypatch):
    changed_file = _write_repo(tmp_path)
    monkeypatch.delenv("NEXUS_VALUE_HIDDEN_VERIFIER", raising=False)

    report = build_preflight_report(tmp_path, changed_file=changed_file)

    assert report["ready_for_benchmark"] is False
    contracts = {item["id"]: item for item in report["benchmark_contract_matrix"]}
    assert contracts["P3"]["status"] == "blocked"
    assert contracts["P3"]["evidence"]["hidden_verifier_enabled"] is False


def test_preflight_cli_writes_report(tmp_path, monkeypatch):
    changed_file = _write_repo(tmp_path)
    output = tmp_path / "preflight.json"
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--changed-file",
            changed_file,
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ready_for_benchmark"] is True
