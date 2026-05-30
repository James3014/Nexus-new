import pytest
from pathlib import Path
from nexus.services.local_heal.pipeline import HealPipeline, HealContext

def test_pipeline_successful_flow(tmp_path):
    # 建立目標模擬檔案
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")
    
    # 模擬 LLM 完美輸出
    def mock_generate(system, prompt):
        return (
            "FILE: hello.py\n"
            "SEARCH:\n"
            "def hello():\n"
            "    return False\n"
            "REPLACE:\n"
            "def hello():\n"
            "    return True\n"
            "END"
        )
        
    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_id",
        repo_dir=tmp_path,
        problem_statement="Change hello to return True",
        max_tries=1
    )
    
    # 手動塞入定位檔案避免 BM25 檢索不到
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]
    
    res_ctx = pipeline.run(ctx)
    assert not res_ctx.errors
    assert "return True" in res_ctx.final_patch
    assert file_path.read_text(encoding="utf-8") == "def hello():\n    return True\n"
