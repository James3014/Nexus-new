import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 確保能 import nexus
sys.path.insert(0, os.getcwd())

from nexus.services.local_heal.pipeline import HealPipeline, HealContext

def mock_generate(system, user):
    """模擬一個穿上戰甲後，遵循 SolidSearchReplace 協議的完美模型。"""
    # 驗證戰甲是否注入了正確的提示
    if "CONTRACT (SolidSearchReplace v1)" not in system:
        print("FAIL: Protocol contract not found in system prompt!")
        return "ERROR"
    
    if "### DOMAIN KNOWLEDGE: DIRECTIVE_PARSER HARDENING" not in user:
        print("FAIL: Domain knowledge not injected in user prompt!")
        # 這裡不 return ERROR，因為我們想看它是否能正確處理檔案
    
    return """
FILE: dummy.py
<<<<<<< SEARCH
    if v == "NO":
=======
    if v.upper() == "NO":
>>>>>>> REPLACE
"""

def test_surgery_system():
    repo_dir = Path("scratch/dummy_repo").resolve()
    if repo_dir.exists():
        import shutil
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)
    
    dummy_py = repo_dir / "dummy.py"
    dummy_py.write_text("""
def parser(v):
    if v == "NO":
        return False
    return True
""", encoding="utf-8")

    # 假裝複現成功
    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    
    ctx = HealContext(
        instance_id="dummy-task",
        repo_dir=repo_dir,
        problem_statement="The QDP parser command 'NO' should be case-insensitive.",
        repro_script="import sys; sys.exit(1)" # 非零退出碼表示複現成功
    )
    
    # 執行管線
    print("🚀 Running surgery system test...")
    final_ctx = pipeline.run(ctx)
    
    # 驗證
    new_content = dummy_py.read_text()
    if 'v.upper() == "NO"' in new_content:
        print("✅ SUCCESS: File patched correctly via SolidSearchReplaceProtocol!")
    else:
        print("❌ FAILED: File not patched!")
        print(f"Content:\n{new_content}")
        print(f"Error Reason: {final_ctx.failure_reason}")

if __name__ == "__main__":
    test_surgery_system()
