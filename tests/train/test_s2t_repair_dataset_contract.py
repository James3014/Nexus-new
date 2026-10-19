#!/usr/bin/env python3
"""
🧪 Test S2T Repair Dataset Contract
驗證 s2t_3b_repair_v2.jsonl 修復數據集之結構完備性與 schema 合規性，防止髒資料進入微調。

#1926: the original test read the untracked, host-generated
.nexus/training/s2t_3b_repair_v2.jsonl, which no host still has. It now builds the
dataset hermetically with scripts/train/build_s2t_repair_dataset.py in a temporary
working directory, from 35 SFT rows and 33 shadow-eval failures that include every
malformed shape the builder must repair, and applies the same contract checks to
the builder's output.
"""
import json
from pathlib import Path

import pytest

from scripts.train import build_s2t_repair_dataset as builder

# 允許的驗證器
ALLOWED_VERIFIERS = ["pytest", "claim_gate", "delivery_gate", "hidden_verifier"]

_ERROR_TYPES = (
    "missing_abstain_reason",
    "string_none_instead_of_null",
    "freeform_verifier_name",
    "missing_required_field",
    "other",
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _build_inputs(root: Path) -> None:
    sft_rows = [
        {
            "task_id": f"s2t-{i:02d}",
            "input": {"candidates": [f"c{i}"]},
            "target": {
                "selected_candidate_id": f"c{i}",
                "selection_reason_codes": ["R1"],
                "required_verifier": "pytest",
                "abstain_reason": None,
            },
        }
        for i in range(35)
    ]
    # Anchor rows with schema defects the builder must normalise.
    sft_rows[33]["target"] = {"selected_candidate_id": "c33"}
    sft_rows[34]["target"]["required_verifier"] = "none"
    failures = []
    for i in range(33):
        error_type = _ERROR_TYPES[i % len(_ERROR_TYPES)]
        correct_target: dict | None = {
            "selected_candidate_id": f"c{i}",
            "selection_reason_codes": ["R1"],
            "required_verifier": "claim_gate",
            "abstain_reason": None,
        }
        assert correct_target is not None
        if error_type == "string_none_instead_of_null":
            correct_target["required_verifier"] = "none"
        elif error_type == "freeform_verifier_name":
            correct_target["required_verifier"] = "run the unit tests"
        elif error_type == "missing_required_field":
            del correct_target["abstain_reason"]
            del correct_target["selection_reason_codes"]
        elif error_type == "other":
            correct_target = None  # falls back to the SFT target
        failures.append(
            {
                "task_id": f"s2t-{i:02d}",
                "error_type": error_type,
                "input": {"candidates": [f"c{i}"]},
                "prediction": {"selected_candidate_id": "wrong"},
                "correct_target": correct_target,
            }
        )
    _write_jsonl(root / ".nexus/training/s2t_3b_student_v1.jsonl", sft_rows)
    _write_jsonl(root / ".nexus/metrics/s2t_shadow_eval_failures.jsonl", failures)


def test_s2t_repair_dataset_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _build_inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    builder.main()

    dataset_path = tmp_path / ".nexus/training/s2t_3b_repair_v2.jsonl"
    assert dataset_path.exists(), f"Repair dataset v2 not found at {dataset_path}"

    rows = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    # 確保 row 大於等於 33 筆 (33 筆 failures)
    assert len(rows) >= 33, f"Expected at least 33 repair rows, got {len(rows)}"
    assert sum(1 for r in rows if r["error_type"] != "none") == 33

    for idx, row in enumerate(rows):
        # 1. 驗證 5 大基本欄位存在性
        for field in ["input", "bad_prediction", "error_type", "correct_target", "contract_reminder"]:
            assert field in row, f"Row {idx} is missing field: {field}"

        # 2. 驗證 correct_target 的 S2T JSON 結構
        target = row["correct_target"]
        assert isinstance(target, dict), f"Row {idx} correct_target must be a dictionary"

        # 驗證 4 個 required keys
        for key in ["selected_candidate_id", "selection_reason_codes", "required_verifier", "abstain_reason"]:
            assert key in target, f"Row {idx} correct_target is missing key: {key}"

        # 3. 驗證 required_verifier enum
        verifier = target["required_verifier"]
        assert verifier is None or verifier in ALLOWED_VERIFIERS, (
            f"Row {idx} has invalid required_verifier: '{verifier}'. "
            f"Must be one of {ALLOWED_VERIFIERS} or null."
        )

    card = json.loads(
        (tmp_path / ".nexus/training/s2t_3b_repair_v2_dataset_card.json").read_text(encoding="utf-8")
    )
    assert card["total_rows"] == len(rows)
    assert card["failed_rows_integrated"] == 33
