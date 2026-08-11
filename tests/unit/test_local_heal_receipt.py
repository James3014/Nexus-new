import json

import pytest

from nexus.services.local_heal.pipeline import HealContext
from nexus.services.local_heal.receipt import (
    canonical_run_group,
    write_repair_receipt,
)


def test_write_repair_receipt_records_gate_and_evidence(tmp_path):
    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="fix required column error",
        final_patch="--- a/pkg/file.py\n+++ b/pkg/file.py\n@@ -1 +1 @@\n-a\n+b\n",
        repro_script="raise AssertionError('bug')\n",
        repro_evidence="AssertionError: bug reproduced",
        evaluation_report="=== VISIBLE TEST REPORT ===\n[PASS] python3 reproduce_bug.py\n",
        reproduced=True,
        hidden_verifier_passed=True,
        runner_completed=True,
        solve_eligible=True,
        model_decisions=[{"phase": "patch", "model": "qwen2.5-coder:14b", "timeout_seconds": 180}],
    )

    receipt_path = write_repair_receipt(
        ctx,
        model_name="qwen2.5-coder:14b",
        reports_root=tmp_path / "reports",
        run_group="baseline-a",
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.local_heal.repair_receipt.v1"
    assert payload["instance_id"] == "astropy__astropy-13033"
    assert payload["gate_passed"] is True
    assert payload["patch_paths"] == ["pkg/file.py"]
    assert "patch.diff" in payload["evidence_refs"]
    assert payload["telemetries"]["model_decisions"][0]["timeout_seconds"] == 180
    assert (receipt_path.parent / "patch.diff").exists()


def test_write_repair_receipt_does_not_infer_reproduced_from_evidence(tmp_path):
    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="bug not physically reproduced",
        repro_script="print('not reproduced')\n",
        repro_evidence="script ran but exited zero",
        reproduced=False,
        runner_completed=True,
        solve_eligible=False,
        failure_reason="REPRO_NOT_REPRODUCED",
    )

    receipt_path = write_repair_receipt(ctx, reports_root=tmp_path / "reports", run_group="repro-b")

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["reproduced"] is False
    assert payload["failure_reason"] == "REPRO_NOT_REPRODUCED"


def test_write_repair_receipt_records_env_resolution(tmp_path):
    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="version parity blocked",
        runner_completed=True,
        solve_eligible=False,
        failure_reason="ASTROPY_VERSION_PARITY_MISSING",
        env_resolution={
            "profile": "astropy-legacy",
            "ready": False,
            "reason": "ASTROPY_VERSION_PARITY_MISSING",
            "python_executable": "",
            "probes": [{"candidate": "python3.9", "status": "missing"}],
        },
    )

    receipt_path = write_repair_receipt(ctx, reports_root=tmp_path / "reports", run_group="env-c")

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["failure_reason"] == "ASTROPY_VERSION_PARITY_MISSING"
    assert payload["telemetries"]["env_resolution"]["ready"] is False
    assert payload["telemetries"]["env_resolution"]["probes"][0]["candidate"] == "python3.9"


def test_write_repair_receipt_records_resolved_python_command(tmp_path):
    ctx = HealContext(
        instance_id="astropy__astropy-12907",
        repo_dir=tmp_path,
        problem_statement="verify with resolved python",
        repro_script="raise AssertionError('bug')\n",
        python_executable="/opt/python3.9",
        runner_completed=True,
        solve_eligible=False,
        failure_reason="VERIFICATION_FAILED",
    )

    receipt_path = write_repair_receipt(
        ctx, reports_root=tmp_path / "reports", run_group="python-d"
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["commands"] == ["/opt/python3.9 reproduce_bug.py"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        ".",
        "..",
        "../escape",
        "nested/group",
        "nested\\group",
        "bad\nvalue",
        "bad..value",
    ],
)
def test_canonical_run_group_rejects_unsafe_values_before_writes(tmp_path, value):
    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="run-group validation",
    )
    with pytest.raises(ValueError):
        write_repair_receipt(ctx, reports_root=tmp_path / "reports", run_group=value)
    assert not (tmp_path / "reports").exists()


def test_canonical_run_group_preserves_distinct_valid_identities(tmp_path):
    assert canonical_run_group("group-a") == "group-a"
    assert canonical_run_group("group_b.2") == "group_b.2"

    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="run-group validation",
    )
    first = write_repair_receipt(ctx, reports_root=tmp_path / "reports", run_group="group-a")
    second = write_repair_receipt(ctx, reports_root=tmp_path / "reports", run_group="group-b")
    assert first.parent != second.parent


def test_build_repair_receipt_rejects_unsafe_run_group_before_receipt(tmp_path):
    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="run-group construction validation",
    )
    with pytest.raises(ValueError):
        from nexus.services.local_heal.receipt import build_repair_receipt

        build_repair_receipt(ctx, run_group="../escape")


def test_build_repair_receipt_canonicalizes_valid_run_group(tmp_path):
    ctx = HealContext(
        instance_id="astropy__astropy-13033",
        repo_dir=tmp_path,
        problem_statement="run-group construction validation",
    )
    from nexus.services.local_heal.receipt import build_repair_receipt

    receipt = build_repair_receipt(ctx, run_group="build-group")
    assert receipt["run_group"] == "build-group"
