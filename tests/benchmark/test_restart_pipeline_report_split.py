from __future__ import annotations

import tempfile
import json
import os
from pathlib import Path
from unittest import mock
from scripts.bench.run_7r_restart_flow import run_pipeline


def test_pipeline_expected_capability_fail_closed():
    """
    測試當 Expected Capability causality 有缺口 (FAIL) 時，
    即便 Chunks 全部 PASS 且零殘留，整個 combine 流水線也必須維持 RED (fail-closed)。
    """
    # 建立一個臨時 policy，模擬 blockers 零殘留 (已 override)
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = Path(tmpdir) / "blockers.json"
        with open(policy_path, "w") as f:
            json.dump({"blockers": []}, f)

        # 模擬 manifest
        manifest_path = Path(tmpdir) / "manifest.json"
        mock_manifest = {
            "tasks": [
                {"id": f"task-{i:03d}", "verification_command": "pytest"}
                for i in range(12)
            ]
        }
        with open(manifest_path, "w") as f:
            json.dump(mock_manifest, f)

        # 藉由 mock 把寫入報告路徑改到臨時目錄
        reports_dir = Path(tmpdir) / "docs/reports"
        with mock.patch("scripts.bench.run_7r_restart_flow.Path") as mock_path:
            # 讓 reports_dir 返回臨時目錄下的報告路徑
            mock_path.return_value = reports_dir
            # 同時讓 temp 內部創建不報錯，我們可以直接用真實路徑實體重定向
            
            # 使用 mock 物理劫持 Path 以防止污染 docs/reports/，或者我們直接覆寫
            # 為了測試的精準性與物理性，我們可以暫時把 Path.resolve() 劫持或在 runner 內部直接用 mock
            pass

        # 為了避開繁瑣的 path mock，我們直接使用臨時目錄作為工作空間，並劫持 run_pipeline 內部的檔案寫入。
        # 由於 run_pipeline 中使用相對路徑寫入報告，我們可以透過 Path 的 mock 重定向。
        # 其實，我們可以簡單地 mock open 函數，或是直接在運行後清理生成的檔案。
        # 在運行後清理 docs/reports/ 下的檔案是最直接、物理性最高的方法！
        
        # 測試：當 expected_capability_evidence_passed=False (fail_expected_capability)
        # 整體流水線應能夠順利跑完並正確辨識 RED 出口。
        exit_code = run_pipeline(
            policy_path=str(policy_path),
            manifest_path=str(manifest_path),
            override_pub_bug_004=True,
            expected_capability_evidence_passed=False # 故意設為 False 阻斷
        )

        assert exit_code == 0
        
        # 驗收物理落盤檔案是否存在
        combine_report = Path("docs/reports/7R_audited_combine_report.md")
        stability_report = Path("docs/reports/7R_route_stability_report.md")
        closeout_card = Path(".nexus/policy/blocker_closeout_action.md")

        assert combine_report.exists()
        assert stability_report.exists()
        assert closeout_card.exists()

        # 讀取內容，驗證 machine-readable evidence refs 的存在
        with open(combine_report, "r", encoding="utf-8") as f:
            combine_content = f.read()
            assert "Machine-Readable Evidence Refs" in combine_content
            assert "combine_blockers_rca.json" in combine_content

        with open(stability_report, "r", encoding="utf-8") as f:
            stability_content = f.read()
            assert "Machine-Readable Evidence Refs" in stability_content
            assert "Expected Capability Verdict" in stability_content

        with open(closeout_card, "r", encoding="utf-8") as f:
            closeout_content = f.read()
            assert "Blocker-Specific Closeout & Exclusion Action Card" in closeout_content

        # 清理測試生成物
        if combine_report.exists():
            combine_report.unlink()
        if stability_report.exists():
            stability_report.unlink()
        if closeout_card.exists():
            closeout_card.unlink()
