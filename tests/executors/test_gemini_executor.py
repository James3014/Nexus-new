from pathlib import Path
import json
import pytest
from nexus.executors.gemini import GeminiExecutor
from nexus.executors.protocol import ExecutorInput, ContextPackSchema, ExecutorStatusEnum, ProviderErrorType

def test_gemini_executor_parse_success(tmp_path):
    """驗證 GeminiExecutor 是否能正確從 NEXUS_JSON 標記中提取 Payload。"""
    output_file = tmp_path / "agent_output.txt"
    payload = {
        "status": "PASS",
        "patch_generated": True,
        "files_touched": ["main.py"],
        "summary": "Fixed the bug.",
        "patch": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print(0)\n+print(1)",
        "diagnosis": "Off-by-one error.",
        "tokens_used": 150
    }
    content = f"Some preamble before the markers.\n<NEXUS_JSON_BEGIN>\n{json.dumps(payload)}\n<NEXUS_JSON_END>\nSome postamble."
    output_file.write_text(content)

    executor = GeminiExecutor(output_source=str(output_file))
    ctx = ContextPackSchema(files={"main.py": "print(0)"})
    inp = ExecutorInput(task_id="T1", phase="repair", workspace_root="/tmp", context_pack=ctx)
    
    out = executor.execute(inp)
    
    assert out.status == ExecutorStatusEnum.SUCCESS
    assert out.patch_generated is True
    assert out.patch_diff == payload["patch"]
    assert "main.py" in out.files_touched
    assert out.meta["tokens_output"] == 150

def test_gemini_executor_missing_markers(tmp_path):
    """驗證當輸出中缺少標記時，應回傳合約違反錯誤。"""
    output_file = tmp_path / "broken_output.txt"
    output_file.write_text("The agent did not output any structured markers.")
    
    executor = GeminiExecutor(output_source=str(output_file))
    ctx = ContextPackSchema(files={})
    inp = ExecutorInput(task_id="T1", phase="repair", workspace_root="/tmp", context_pack=ctx)
    
    out = executor.execute(inp)
    assert out.status == ExecutorStatusEnum.PROVIDER_ERROR
    assert out.provider_error_type == ProviderErrorType.PROVIDER_CONTRACT_VIOLATION
    assert "Missing <NEXUS_JSON_BEGIN>" in out.summary

def test_gemini_executor_quota_error(tmp_path):
    """驗證 Quota 錯誤的自動分類。"""
    output_file = tmp_path / "quota_error.txt"
    output_file.write_text("Error: 429 Resource has been exhausted (e.g. check your quota).")
    
    executor = GeminiExecutor(output_source=str(output_file))
    ctx = ContextPackSchema(files={})
    inp = ExecutorInput(task_id="T1", phase="repair", workspace_root="/tmp", context_pack=ctx)
    
    out = executor.execute(inp)
    assert out.status == ExecutorStatusEnum.PROVIDER_ERROR
    assert out.provider_error_type == ProviderErrorType.QUOTA_LIMIT
