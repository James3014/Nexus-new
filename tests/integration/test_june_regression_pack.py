from __future__ import annotations

import json
import pytest
from pathlib import Path
from scripts.local_heal.run_june_regression_pack import run_pack, repo_root

def test_june_regression_pack_governance_integrity() -> None:
    """
    Phase 56F.1 — Regression Gate Integrity Test
    
    這個測試的目的不是驗證「本地模型解題率」。
    目的是驗證「框架治理欄位是否正確標記、防假宣稱」。
    
    真正的解題率要等到 real_model mode 下，由本地 Qwen + Nexus pipeline 執行。
    """
    res = run_pack(replay_mode="mock_oracle")

    assert res["status"] == "completed"
    results = res["results"]
    # 6 個任務全部完成（不管是否 pass）
    assert len(results) == 6, f"Expected 6 tasks, got {len(results)}"

    mapped = {r["task_id"]: r for r in results}

    # ======================================================
    # Gate 1: 治理欄位完整性 (所有任務)
    # ======================================================
    required_fields = [
        "task_id", "june_group", "replay_mode", "mock_oracle_used",
        "real_model_called", "oracle_patch_used", "final_classification",
        "final_verdict", "used_heal_orchestrator_run", "patch_applied_evidence",
        "environment_sync_success",
    ]
    for task_id, r in mapped.items():
        for field in required_fields:
            assert field in r, f"Task {task_id} missing governance field: {field}"

    # ======================================================
    # Gate 2: 防假宣稱 (最重要) — 任何 mock_oracle 任務絕不能宣稱 MAINLINE_RECOVERED
    # ======================================================
    for task_id, r in mapped.items():
        fc = r["final_classification"]
        assert fc != "MAINLINE_RECOVERED", (
            f"GOVERNANCE VIOLATION: {task_id} claims MAINLINE_RECOVERED in mock_oracle mode! "
            f"Got: {fc}"
        )
        assert fc != "FULL_MAINLINE_RECOVERED", (
            f"GOVERNANCE VIOLATION: {task_id} claims FULL_MAINLINE_RECOVERED in mock_oracle mode! "
            f"Got: {fc}"
        )

    # ======================================================
    # Gate 3: mock_oracle metadata 一致性
    # ======================================================
    for task_id, r in mapped.items():
        assert r["replay_mode"] == "mock_oracle", f"{task_id}: replay_mode mismatch"
        assert r["mock_oracle_used"] is True, f"{task_id}: mock_oracle_used must be True"
        assert r["real_model_called"] is False, f"{task_id}: real_model_called must be False in mock_oracle"
        assert r["oracle_patch_used"] is True, f"{task_id}: oracle_patch_used must be True"

    # ======================================================
    # Gate 4: final_classification 只能是合法的 mock_oracle 標籤
    # ======================================================
    VALID_MOCK_ORACLE_CLASSIFICATIONS = {
        "MOCK_ORACLE_REPLAY_PASS",
        "MOCK_ORACLE_REPLAY_FAIL",
        "NOT_REPLAYABLE",
    }
    for task_id, r in mapped.items():
        assert r["final_classification"] in VALID_MOCK_ORACLE_CLASSIFICATIONS, (
            f"{task_id}: invalid mock_oracle classification: {r['final_classification']}. "
            f"Must be one of {VALID_MOCK_ORACLE_CLASSIFICATIONS}"
        )

    # ======================================================
    # Gate 5: Group 標記正確性
    # ======================================================
    assert mapped["astropy__astropy-13236"]["june_group"] == "A_PASSED"
    assert mapped["astropy__astropy-12907"]["june_group"] == "A_PASSED"
    assert mapped["astropy__astropy-14182"]["june_group"] == "B_UNSOLVED"
    assert mapped["sympy__sympy-13852"]["june_group"] == "B_UNSOLVED"
    assert mapped["astropy__astropy-13453"]["june_group"] == "B_UNSOLVED"
    assert mapped["astropy__astropy-13579"]["june_group"] == "C_INFRA"

    # ======================================================
    # Gate 6: Group C (INFRA) 任務必須標記為 INFRA_BLOCKED
    # ======================================================
    t_13579 = mapped["astropy__astropy-13579"]
    assert t_13579["final_verdict"] == "INFRA_BLOCKED", (
        f"astropy-13579 should be INFRA_BLOCKED (expected C-extension failure), got: {t_13579['final_verdict']}"
    )
    assert t_13579["receipt_coverage"] == 0.0

    # ======================================================
    # Gate 7: HealOrchestrator 呼叫標記
    # ======================================================
    for task_id, r in mapped.items():
        # 只有 INFRA_BLOCKED (環境同步失敗) 才允許 used_heal_orchestrator_run = False
        if r["final_verdict"] != "INFRA_BLOCKED" or r.get("environment_sync_success") is True:
            assert r["used_heal_orchestrator_run"] is True, (
                f"{task_id}: should have used HealOrchestrator.run(), got False"
            )

    # ======================================================
    # Gate 8: patch_applied_evidence 欄位完備性
    # ======================================================
    required_evidence_fields = [
        "candidate_patch_hash", "applied_patch_hash",
        "selected_candidate_hash_matches_applied", "apply_receipt_status",
        "patched_file_hash_before", "patched_file_hash_after",
        "verifier_ran_after_apply", "verifier_workspace_path", "applied_diff_present",
    ]
    for task_id, r in mapped.items():
        ev = r.get("patch_applied_evidence", {})
        if ev:  # 有執行 verifier 的任務
            for ef in required_evidence_fields:
                assert ef in ev, f"{task_id} patch_applied_evidence missing field: {ef}"

    # ======================================================
    # Gate 9: results.jsonl 完整輸出
    # ======================================================
    jsonl_path = Path(repo_root) / "artifacts" / "runtime" / "june_regression_pack_v0" / "results.jsonl"
    assert jsonl_path.exists(), "results.jsonl not found"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6, f"Expected 6 result lines in JSONL, got {len(lines)}"

    # 每行都是有效 JSON
    for i, line in enumerate(lines):
        row = json.loads(line)
        assert "task_id" in row, f"JSONL line {i} missing task_id"
        assert "final_classification" in row, f"JSONL line {i} missing final_classification"
        assert row["final_classification"] != "MAINLINE_RECOVERED", (
            f"GOVERNANCE VIOLATION in JSONL line {i}: {row['task_id']} claims MAINLINE_RECOVERED"
        )

    # ======================================================
    # 正直報告：顯示通過/阻斷/失敗分布（不偽造結果）
    # ======================================================
    group_a = [r for r in results if r["june_group"] == "A_PASSED"]
    group_b = [r for r in results if r["june_group"] == "B_UNSOLVED"]
    group_c = [r for r in results if r["june_group"] == "C_INFRA"]

    group_a_pass = sum(1 for r in group_a if r["final_classification"] == "MOCK_ORACLE_REPLAY_PASS")
    group_b_pass = sum(1 for r in group_b if r["final_classification"] == "MOCK_ORACLE_REPLAY_PASS")
    group_a_infra = sum(1 for r in group_a if r["final_verdict"] == "INFRA_BLOCKED")
    group_b_infra = sum(1 for r in group_b if r["final_verdict"] == "INFRA_BLOCKED")

    print(f"\n📊 Governance Integrity Report (mock_oracle mode):")
    print(f"   Group A (防退化): {group_a_pass}/{len(group_a)} mock replay pass | {group_a_infra} INFRA_BLOCKED")
    print(f"   Group B (新通過): {group_b_pass}/{len(group_b)} mock replay pass | {group_b_infra} INFRA_BLOCKED")
    print(f"   Group C (INFRA):  {len(group_c)}/{len(group_c)} correctly labeled INFRA_BLOCKED")
    print(f"\n⚠️  NOTE: Mock Oracle replay pass ≠ real model solve rate.")
    print(f"   Real model solve rate requires real_model mode with local Qwen + Nexus pipeline.")
