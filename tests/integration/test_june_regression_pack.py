from __future__ import annotations

import json
import pytest
from pathlib import Path
from scripts.local_heal.run_june_regression_pack import run_pack, repo_root

def test_june_regression_pack_replay() -> None:
    res = run_pack()
    
    assert res["status"] == "completed"
    results = res["results"]
    assert len(results) == 5
    
    mapped = {r["task_id"]: r for r in results}
    
    # ==================== Group A (防退化) ====================
    
    # 1. astropy-13236
    t_13236 = mapped["astropy__astropy-13236"]
    assert t_13236["june_group"] == "A_PASSED"
    # Schema check
    assert "environment_sync_success" in t_13236
    assert "pip_available" in t_13236
    
    if t_13236["final_verdict"] == "PASSED":
        assert t_13236["canonical_span_source"] in ("unified_diff", "locked_search")
        assert t_13236["verifier_status"] == "pass"
        assert t_13236["receipt_coverage"] == 1.0
        assert t_13236["used_heal_orchestrator"] is True
        assert t_13236["used_qwen_backend_seam"] is True
        assert t_13236["public_claim_allowed"] is False
    else:
        assert t_13236["final_verdict"] == "INFRA_BLOCKED"
        assert t_13236["used_heal_orchestrator"] is False
        
    # 2. astropy-12907
    t_12907 = mapped["astropy__astropy-12907"]
    assert t_12907["june_group"] == "A_PASSED"
    
    if t_12907["final_verdict"] == "PASSED":
        assert t_12907["canonical_span_source"] in ("ast_boundary", "locked_search")
        assert t_12907["used_granular_localizer"] is True
        assert t_12907["verifier_status"] == "pass"
        assert t_12907["receipt_coverage"] == 1.0
        assert t_12907["used_heal_orchestrator"] is True
        assert t_12907["used_qwen_backend_seam"] is True
        assert t_12907["public_claim_allowed"] is False
    else:
        assert t_12907["final_verdict"] == "INFRA_BLOCKED"
        assert t_12907["used_heal_orchestrator"] is False

    # ==================== Group B (新通過，測主線恢復) ====================
    
    # 3. astropy-14182
    t_14182 = mapped["astropy__astropy-14182"]
    assert t_14182["june_group"] == "B_UNSOLVED"
    
    if t_14182["final_verdict"] == "PASSED":
        assert t_14182["current_status"] == "pass"
        assert t_14182["verifier_status"] == "pass"
        assert t_14182["receipt_coverage"] == 1.0
        assert t_14182["used_heal_orchestrator"] is True
        assert t_14182["used_qwen_backend_seam"] is True
        assert t_14182["public_claim_allowed"] is False
        assert t_14182["side_lane_only"] is False
    else:
        assert t_14182["final_verdict"] == "INFRA_BLOCKED"
        assert t_14182["used_heal_orchestrator"] is False

    # 4. sympy-13852
    t_13852 = mapped["sympy__sympy-13852"]
    assert t_13852["june_group"] == "B_UNSOLVED"
    
    # Check contamination guard fields
    assert "source_tree_clean_before_run" in t_13852
    assert "manual_source_edit_detected" in t_13852
    
    if t_13852["final_verdict"] == "PASSED":
        assert t_13852["current_status"] == "pass"
        assert t_13852["verifier_status"] == "pass"
        assert t_13852["receipt_coverage"] == 1.0
        assert t_13852["used_heal_orchestrator"] is True
        assert t_13852["used_qwen_backend_seam"] is True
        assert t_13852["public_claim_allowed"] is False
        assert t_13852["side_lane_only"] is False
    else:
        assert t_13852["final_verdict"] == "INFRA_BLOCKED"
        assert t_13852["used_heal_orchestrator"] is False

    # ==================== Group C (測環境阻斷) ====================
    
    # 5. astropy-13579
    t_13579 = mapped["astropy__astropy-13579"]
    assert t_13579["june_group"] == "C_INFRA"
    assert t_13579["final_verdict"] == "INFRA_BLOCKED"
    assert t_13579["used_heal_orchestrator"] is False
    assert t_13579["used_qwen_backend_seam"] is False
    assert t_13579["receipt_coverage"] == 0.0
    
    # 6. 確保 output results.jsonl 存在且欄位完備
    jsonl_path = Path(repo_root) / "artifacts" / "runtime" / "june_regression_pack_v0" / "results.jsonl"
    assert jsonl_path.exists()
    
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
