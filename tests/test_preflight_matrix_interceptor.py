from __future__ import annotations

import json
import pytest
from nexus.learning.skill_fit_ablation_core import build_skill_fit_execution_matrix

def test_preflight_matrix_interceptor_unsupported_external(tmp_path):
    # 創建一個含有 external 且缺少 setup_adapter 的任務清單 manifest 檔案
    manifest_file = tmp_path / "tasks.json"
    tasks_data = {
        "tasks": [
            {
                "id": "task_external_no_adapter",
                "repo_kind": "external",
                "setup_adapter": None,  # 無 setup adapter
                "expected_capabilities": ["browse"]
            }
        ]
    }
    manifest_file.write_text(json.dumps(tasks_data), encoding="utf-8")

    # 模擬 plan 物件
    plan = {
        "schema": "nexus.skill_fit_ablation_plan.v1",
        "capability": "browse",
        "arms": [
            {
                "arm_id": "browse::ablation",
                "arm_type": "skill_ablation",
                "skill_id": "browse_skill",
                "runtime_eligible": True,
                "ablation_eligible": True,
            }
        ]
    }

    # 傳入 task_refs
    task_refs = [
        {
            "manifest": str(manifest_file),
            "task_id": "task_external_no_adapter"
        }
    ]

    # 呼叫 build_skill_fit_execution_matrix
    matrix = build_skill_fit_execution_matrix(plan, task_refs=task_refs)

    # 斷言因為 repo_kind 是 external 且缺乏 setup_adapter，matrix status 必須熔斷回傳 "RETURN"
    assert matrix["status"] == "RETURN"
    assert "unsupported external task" in matrix.get("summary", {}).get("block_reason", "").lower()
