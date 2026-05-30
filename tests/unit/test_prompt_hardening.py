import pytest
from nexus.services.local_heal.pipeline import HealContext, HealPipeline
from nexus.services.local_heal.errors import PatchError, PatchErrorKind

def test_system_prompt_contains_anti_apology(tmp_path):
    # 由於我們沒有 Mock LLM，我們只運行到 LLM 之前，或者 mock ollama_generate 拋出異常
    def mock_generate(sys_p, user_p):
        raise ValueError("Stop execution")
        
    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="astropy-13398",
        problem_statement="test rotation_matrix",
        repo_dir=tmp_path
    )
    
    # 這裡我們不需要跑完整的 run，我們只要 mock 住 _localize 並呼叫 run 的初始化部分
    def mock_localize(c):
        c.localized_files = [("astropy/coordinates/matrix_utilities.py", "def rotation_matrix():\n    pass")]
        return c
        
    pipeline._localize = mock_localize
    
    try:
        pipeline.run(ctx)
    except ValueError:
        pass
    
    assert "NEVER apologize" in ctx.system_prompt
    assert "NEVER say you cannot help" in ctx.system_prompt


def test_no_blocks_retry_reduces_to_top1_file():
    def mock_generate(sys_p, user_p):
        return ""
        
    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="astropy-13398",
        problem_statement="test rotation_matrix",
        repo_dir=None
    )
    ctx.localized_files = [
        ("file1.py", "content1"),
        ("file2.py", "content2"),
        ("file3.py", "content3")
    ]
    ctx.user_prompt = "Bug Report:\n...\n\nSource Code:\nfile1, file2, file3"
    
    error = PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="No blocks found")
    
    # 測試 _handle_retry
    updated_ctx = pipeline._handle_retry(ctx, error)
    
    # 應該被縮減為僅含 1 個檔案 (top-1)
    assert len(updated_ctx.localized_files) == 1
    assert updated_ctx.localized_files[0][0] == "file1.py"
    assert "file2.py" not in updated_ctx.user_prompt
