from __future__ import annotations

import json
import subprocess


def _run_json_command(args: list[str]) -> dict:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_hallucination_guard_drift_accepts_output_json_flag():
    payload = _run_json_command(["uv", "run", "python", "scripts/ops/hallucination_guard_drift.py", "--output-json"])

    assert payload["schema_version"] == "nexus_hallucination_guard_drift.v1"
    assert payload["passed"] is True


def test_brain_hub_audit_accepts_output_json_flag():
    payload = _run_json_command(
        [
            "uv",
            "run",
            "python",
            "scripts/ops/brain_hub_audit.py",
            "--manifest",
            "docs/ops/brain_hub_manifest.json",
            "--output-json",
        ]
    )

    assert payload["schema_version"] == "nexus_brain_hub_audit.v1"
    assert payload["passed"] is True


def test_render_brain_hub_coverage_accepts_output_json_flag(tmp_path):
    output = tmp_path / "coverage.md"
    payload = _run_json_command(
        [
            "uv",
            "run",
            "python",
            "scripts/ops/render_brain_hub_coverage.py",
            "--manifest",
            "docs/ops/brain_hub_manifest.json",
            "--output",
            str(output),
            "--output-json",
        ]
    )

    assert payload["passed"] is True
    assert payload["output"] == str(output)
    assert output.exists()
