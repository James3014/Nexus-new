from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.s2t_adoption_gate import evaluate_metrics_file, main


def test_s2t_adoption_gate_allows_strict_opt_in(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "eligible_rows": 30,
                "selector_override_verified_rate": 0.72,
                "original_top1_verified_rate": 0.5,
                "trust_mismatch_delta": 0.0,
                "public_claim_precision_delta": 0.0,
                "heldout_win_rate": 0.6,
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_metrics_file(metrics)

    assert report["passed"] is True
    assert report["decision"]["status"] == "strict_opt_in"


def test_s2t_adoption_gate_blocks_weak_shadow_data(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "eligible_rows": 3,
                "selector_override_verified_rate": 0.72,
                "original_top1_verified_rate": 0.5,
                "trust_mismatch_delta": 0.0,
                "public_claim_precision_delta": 0.0,
                "heldout_win_rate": 0.6,
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_metrics_file(metrics)

    assert report["passed"] is False
    assert report["decision"]["status"] == "shadow_only"
    assert "insufficient_shadow_rows" in report["decision"]["reason_codes"]


def test_s2t_adoption_gate_main_writes_report(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    report = tmp_path / "report.json"
    metrics.write_text(
        json.dumps(
            {
                "eligible_rows": 30,
                "selector_override_verified_rate": 0.72,
                "original_top1_verified_rate": 0.5,
                "trust_mismatch_delta": 0.0,
                "public_claim_precision_delta": 0.0,
                "heldout_win_rate": 0.6,
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--metrics", str(metrics), "--output", str(report)])

    assert rc == 0
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] is True
