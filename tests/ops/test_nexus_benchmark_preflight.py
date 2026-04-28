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


def test_build_preflight_report_passes_without_gemini(tmp_path):
    changed_file = _write_repo(tmp_path)

    report = build_preflight_report(tmp_path, changed_file=changed_file)

    assert report["schema"] == "nexus_benchmark_preflight_readiness_v1"
    assert report["ready_for_benchmark"] is True
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["codeintel_evidence"]["passed"] is True
    assert checks["codeintel_evidence"]["evidence"]["schema_version"] == "codeintel-v1"
    assert checks["rlm_trace_quality"]["evidence"]["rlm_trace_quality_score"] >= 60
    assert checks["jit_promotion_boundary"]["evidence"]["default_switch_allowed"] is False
    assert checks["public_claim_gate"]["evidence"]["fail_gate"]["verdict"] == "FAIL"


def test_build_preflight_report_fails_when_changed_file_is_missing(tmp_path):
    report = build_preflight_report(tmp_path, changed_file="missing.py")

    assert report["ready_for_benchmark"] is False
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["codeintel_evidence"]["passed"] is False
    assert checks["codeintel_evidence"]["reason"] == "changed_file_missing"


def test_preflight_cli_writes_report(tmp_path):
    changed_file = _write_repo(tmp_path)
    output = tmp_path / "preflight.json"

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
