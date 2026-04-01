import pytest
from nexus.engine.pipeline_graph import run_graph_poc

def test_langgraph_self_heal():
    """🛡️ 核驗 LangGraph 的自愈路徑 (A_FAIL -> Memory -> P)"""
    res = run_graph_poc("test task")
    
    # 核驗關鍵位點內容分組。
    assert res["status"] == "ok"
    assert "audit_fail" in res["final_history"]
    assert "memory_refreshed" in res["final_history"]
    assert "audit_pass" in res["final_history"]
    
    # 核驗順序內容分組內容分組。
    # 預期：planned -> coded -> audit_fail -> memory_refreshed -> planned -> coded -> audit_pass
    final_h = res["final_history"]
    assert final_h.index("audit_fail") < final_h.index("memory_refreshed")
    assert final_h.index("memory_refreshed") < final_h.index("audit_pass")
    
    print("✅ LangGraph Self-Heal Verification Passed.")

if __name__ == "__main__":
    test_langgraph_self_heal()
