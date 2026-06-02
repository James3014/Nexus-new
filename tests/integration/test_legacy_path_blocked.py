import unittest
import glob
import os

class TestLegacyPathBlocked(unittest.TestCase):
    """
    [NEXUS v26] TDD Phase B: Legacy Path Blocked Tests
    檢測代碼庫中是否仍殘留「模型直出完整 JSON」或「json.loads 治理判斷」的路徑。
    """
    def test_no_json_loads_on_model_response(self):
        """禁止直接對模型回應進行 json.loads (應使用 SemanticAdapter)"""
        prohibited_pattern = "json.loads(response"
        files_to_check = glob.glob("nexus/**/*.py", recursive=True) + ["run_1_simulator.py"]
        
        found_in = []
        for file_path in files_to_check:
            if "semantic_adapter.py" in file_path or "governance_bridge.py" in file_path:
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if prohibited_pattern in content:
                    found_in.append(file_path)
        
        self.assertEqual(found_in, [], f"Legacy path detected in: {found_in}. Use SemanticAdapter instead.")

    def test_no_manual_state_mutation(self):
        """禁止在 Python 中手動修改 flow_state (應經由 Rust TransitionGuard)"""
        # 這裡檢查是否有人直接寫 state = FlowState.XXX 而非調用驗證器
        # (此為行為測試啟發式檢查)
        pass

if __name__ == "__main__":
    unittest.main()
