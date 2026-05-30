import pytest
from pathlib import Path
from nexus.services.local_heal.pipeline import HealContext, HealPipeline

def test_pipeline_trace_written_on_localize_failure(tmp_path):
    # 建立 mock localizer 會拋出異常
    class BadLocalizer:
        def rank_files(self, *args, **kwargs):
            raise ValueError("BM25 Database Corrupted!")
            
    pipeline = HealPipeline(ollama_generate_fn=lambda sys, p: "")
    pipeline.localizer = BadLocalizer()
    
    ctx = HealContext(
        instance_id="astropy-13236",
        repo_dir=tmp_path,
        problem_statement="Test trace on crash",
        max_tries=1
    )
    
    # 執行 _localize
    res_ctx = pipeline._localize(ctx)
    
    # 不應該 Crash，且 localized_files 應為空
    assert res_ctx.localized_files == []
    
    # 檢查是否寫入了 LOCALIZE_EXCEPTION 至 trace 檔案
    trace_file = Path("/Users/jameschen/Workspace/nexus/scratch/llm_trace.log")
    assert trace_file.exists()
    trace_content = trace_file.read_text(encoding="utf-8")
    assert "LOCALIZE_EXCEPTION" in trace_content
    assert "BM25 Database Corrupted!" in trace_content


def test_pipeline_trace_has_start_and_end(tmp_path):
    # 清理舊日誌以便斷言
    trace_file = Path("/Users/jameschen/Workspace/nexus/scratch/llm_trace.log")
    if trace_file.exists():
        trace_file.unlink()
        
    def mock_generate(sys_p, user_p):
        return ""
        
    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    # mock _localize 避免檢索
    pipeline._localize = lambda c: c
    
    ctx = HealContext(
        instance_id="astropy-13977",
        repo_dir=tmp_path,
        problem_statement="Test start end",
        max_tries=1
    )
    
    pipeline.run(ctx)
    
    assert trace_file.exists()
    trace_content = trace_file.read_text(encoding="utf-8")
    assert "=== PIPELINE START astropy-13977 ===" in trace_content
    assert "=== PIPELINE END astropy-13977" in trace_content
