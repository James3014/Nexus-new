#!/usr/bin/env python3
"""
🧪 Test S2T Repair Dataset Contract
驗證 s2t_3b_repair_v2.jsonl 修復數據集之結構完備性與 schema 合規性，防止髒資料進入微調。
"""
import os
import json
from pathlib import Path

# 允許的驗證器
ALLOWED_VERIFIERS = ["pytest", "claim_gate", "delivery_gate", "hidden_verifier"]

def test_s2t_repair_dataset_contract():
    dataset_path = Path(".nexus/training/s2t_3b_repair_v2.jsonl")
    
    # 如果修復數據集尚未生成，此測試直接跳過或失敗，但在此處要求必須已生成
    assert dataset_path.exists(), f"Repair dataset v2 not found at {dataset_path}"
    
    rows = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                
    # 確保 row 大於等於 33 筆 (33 筆 failures)
    assert len(rows) >= 33, f"Expected at least 33 repair rows, got {len(rows)}"
    
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
