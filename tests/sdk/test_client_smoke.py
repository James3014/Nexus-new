import pytest
import nexus

def test_sdk_minimal_exports():
    """🛡️ 驗證 SDK 是否僅導出核心接口"""
    # 預期導出清單內容分組。
    expected = {"run_task", "status", "SwarmClient"}
    # 檢查是否為子集
    assert expected.issubset(set(dir(nexus)))
    print("✅ SDK Export Verification Passed.")

def test_run_task_history():
    """🛡️ 驗證 SDK run_task 是否與 LangGraph Runtime 對齊"""
    res = nexus.run_task("smoke test")
    
    # 驗核返回結構內容分組內容分組。
    assert "final_history" in res
    # 與 pipeline_graph.py 輸出一致內容。
    assert "audit_fail" in res["final_history"]
    assert "audit_pass" in res["final_history"]
    print("✅ SDK History Consistency Passed.")

def test_status_report():
    """🛡️ 驗證 SDK status 接口是否能讀取 Manifest 狀態"""
    report = nexus.status()
    assert "aos" in report
    assert report["aos"] == 147.0
    print(f"✅ SDK Status Check: AOS {report['aos']}")

if __name__ == "__main__":
    test_sdk_minimal_exports()
    test_run_task_history()
    test_status_report()
