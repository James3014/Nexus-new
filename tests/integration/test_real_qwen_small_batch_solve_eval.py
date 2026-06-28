from __future__ import annotations

import json
import os
import pytest
from pathlib import Path

from scripts.local_heal.run_real_qwen_small_batch_eval import (
    find_ollama_model,
    run_batch_eval,
    repo_root,
)


def test_real_qwen_small_batch_solve_eval_pipeline() -> None:
    model_prefix = "qwen2.5-coder"
    full_model_name = find_ollama_model(model_prefix)
    if not full_model_name:
        pytest.skip(f"Ollama or model {model_prefix} not available locally, skipping real batch eval test.")
        
    res = run_batch_eval()
    
    assert res["status"] == "completed"
    assert res["attempted_count"] == 10
    
    jsonl_path = Path(repo_root) / "artifacts" / "runtime" / "real_qwen_small_batch_eval_v0" / "results.jsonl"
    assert jsonl_path.exists()
    
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    
    forbidden_infra = {
        "local_model_not_called",
        "provider_not_configured",
        "model_name_missing",
        "ollama_http_error",
        "ollama_url_error",
        "ollama_internal_error",
    }
    
    for line in lines:
        item = json.loads(line)
        reason = item.get("fallback_block_reason", "")
        reasons_set = set(reason.split(";")) if reason else set()
        
        # 斷言無基礎設施故障
        infra_failures = reasons_set & forbidden_infra
        assert not infra_failures, f"Task {item['task_id']} hit infrastructure blockers: {infra_failures}"
        
        # 斷言安全政策對齊
        assert item["public_claim_allowed"] is False
        assert item["production_ready"] is False
        assert item["model_called"] is True
        
        # 斷言自癒收據屬性正確儲存且為布林值
        assert "repair_attempted" in item
        assert "repair_success" in item
        assert isinstance(item["repair_attempted"], bool)
        assert isinstance(item["repair_success"], bool)
        
        # 斷言 retry 屬性正確儲存且符合類型規範
        assert "attempt_count" in item
        assert "retry_attempted" in item
        assert "retry_reason" in item
        assert "retry_success" in item
        assert "final_failure_class" in item
        assert isinstance(item["attempt_count"], int)
        assert isinstance(item["retry_attempted"], bool)
        assert isinstance(item["retry_success"], bool)
        assert isinstance(item["retry_reason"], str)
        assert isinstance(item["final_failure_class"], str)
