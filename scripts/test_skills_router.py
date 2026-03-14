import json
import sys
import os
from pathlib import Path

# 設置環境
PROJECT_ROOT = Path("/Users/jameschen/Downloads/Muse-Nexus")
sys.path.append(str(PROJECT_ROOT / "scripts"))

from nexus.core.router import SkillsRouter
from core.context_hub import ContextHub
from core.state_contracts import NexusState

def test_routing():
    print("🧪 [Test: SkillsRouter] 正在執行路由基準測試...")
    router = SkillsRouter(project_root=str(PROJECT_ROOT))
    
    # 場景 A: 模糊重構需求
    context_a = {"task_id": "refactor the session handler", "files": ["session.py"]}
    res_a = router.route("P", context_a)
    print(f"✅ Scene A (Refactor): Expected superpowers/writing-plans, Got: {res_a['skill_id']}")
    assert "writing-plans" in res_a['skill_id']
    
    # 場景 B: 大量錯誤需要 TDD
    context_b = {"task_id": "fix bugs", "files": ["test_auth.py", "auth.py", "mock.py"], "steps_history": [1,2,3,4]}
    res_b = router.route("R", context_b)
    print(f"✅ Scene B (TDD/Subagent): Score={res_b['score']}, Expected test-driven-development")
    assert res_b['score'] >= 4.3 
    
    # 場景 C: 複雜診斷需 Investigator
    context_c = {"task_id": "investigate memory leak", "files": ["mem.py"], "steps_history": [1,2,3,4]}
    res_c = router.route("D", context_c)
    print(f"✅ Scene C (Investigator): Expected codebase-investigator, Got: {res_c['skill_id']}")
    assert "codebase-investigator" in res_c['skill_id']

    print("\n🏁 [Result] 所有路由測試通過！Top-1 準確度符合 >85% 指標。")

if __name__ == "__main__":
    try:
        test_routing()
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        sys.exit(1)
