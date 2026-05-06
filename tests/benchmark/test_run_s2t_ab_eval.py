from __future__ import annotations

import json

from scripts.bench.run_s2t_ab_eval import build_s2t_eval, main


def test_s2t_ab_eval_reports_selector_lift_and_cost_comparability() -> None:
    report = build_s2t_eval(
        [
            {
                "original_top1_candidate_id": "A",
                "s2t_selected_candidate_id": "B",
                "original_top1_verified": False,
                "s2t_selected_verified": True,
                "time_to_verified": 12.0,
                "public_cost_evidence": True,
            },
            {
                "original_top1_candidate_id": "A",
                "s2t_selected_candidate_id": "A",
                "original_top1_verified": True,
                "s2t_selected_verified": True,
                "time_to_verified": 8.0,
                "public_cost_evidence": False,
            },
        ]
    )

    assert report["schema_version"] == "nexus_s2t_ab_eval.v1"
    assert report["eligible_rows"] == 2
    assert report["selector_override_rate"] == 0.5
    assert report["selector_override_verified_rate"] == 1.0
    assert report["original_top1_verified_rate"] == 0.5
    assert report["cost_comparable_rate"] == 0.5


def test_s2t_ab_eval_main_writes_report(tmp_path, capsys) -> None:
    source = tmp_path / "rows.jsonl"
    output = tmp_path / "report.json"
    source.write_text(
        json.dumps(
            {
                "original_top1_candidate_id": "A",
                "s2t_selected_candidate_id": "B",
                "original_top1_verified": False,
                "s2t_selected_verified": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rc = main(["--input", str(source), "--output", str(output)])

    assert rc == 0
    assert json.loads(output.read_text(encoding="utf-8"))["eligible_rows"] == 1
    assert "nexus_s2t_ab_eval.v1" in capsys.readouterr().out
