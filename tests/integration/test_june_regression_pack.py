from __future__ import annotations

import json
import pytest
from pathlib import Path
from scripts.local_heal.run_june_regression_pack import run_pack, repo_root

def test_june_regression_pack_replay() -> None:
    res = run_pack()
    
    assert res["status"] == "completed"
    results = res["results"]
    assert len(results) == 2
    
    # 建立 task_id 索引以利斷言
    mapped = {r["task_id"]: r for r in results}
    
    # 1. 斷言 astropy-13236 歷史與當前狀態
    t_13236 = mapped["astropy__astropy-13236"]
    assert "environment_sync_attempted" in t_13236
    
    if t_13236.get("environment_sync_success") is True:
        assert t_13236["canonical_span_source"] in ("unified_diff", "locked_search")
        assert t_13236["verifier_status"] == "pass"
        assert t_13236["receipt_coverage"] == 1.0
        assert t_13236["used_heal_orchestrator"] is True
        assert t_13236["used_qwen_backend_seam"] is True
        assert t_13236["public_claim_allowed"] is False
    else:
        assert t_13236["current_status"] == "INFRA_BLOCKED"
        assert t_13236["receipt_coverage"] == 0.0
        assert t_13236["used_heal_orchestrator"] is False
        assert t_13236["used_qwen_backend_seam"] is False
        assert t_13236["final_blocker"] in ("INSTALLATION_FAILED", "SUBPROCESS_EXCEPTION")
        assert t_13236["public_claim_allowed"] is False
        
    # 2. 斷言 astropy-12907 歷史與當前狀態
    t_12907 = mapped["astropy__astropy-12907"]
    assert "environment_sync_attempted" in t_12907
    
    if t_12907.get("environment_sync_success") is True:
        assert t_12907["canonical_span_source"] in ("ast_boundary", "locked_search")
        assert t_12907["used_granular_localizer"] is True
        assert t_12907["verifier_status"] == "pass"
        assert t_12907["receipt_coverage"] == 1.0
        assert t_12907["used_heal_orchestrator"] is True
        assert t_12907["used_qwen_backend_seam"] is True
        assert t_12907["public_claim_allowed"] is False
    else:
        assert t_12907["current_status"] == "INFRA_BLOCKED"
        assert t_12907["receipt_coverage"] == 0.0
        assert t_12907["used_heal_orchestrator"] is False
        assert t_12907["used_qwen_backend_seam"] is False
        assert t_12907["final_blocker"] in ("INSTALLATION_FAILED", "SUBPROCESS_EXCEPTION")
        assert t_12907["public_claim_allowed"] is False
        
    # 3. 確保 output results.jsonl 存在且欄位完備
    jsonl_path = Path(repo_root) / "artifacts" / "runtime" / "june_regression_pack_v0" / "results.jsonl"
    assert jsonl_path.exists()
    
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
