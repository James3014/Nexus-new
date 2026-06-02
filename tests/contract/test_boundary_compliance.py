import unittest
import sys
import os

# [NEXUS v2.3] Boundary Compliance and Least Privilege Tests
# Focus: Ensuring Rust kernel modules are properly isolated and errors are mapped.

class TestBoundaryCompliance(unittest.TestCase):
    def setUp(self):
        sys.path.append(os.path.abspath("target/release"))
        import nexus_core
        self.core = nexus_core

    def test_error_transparency_from_rust_to_python(self):
        """[LangSec] 驗證：Rust 的 Recognizer 拒絕結果必須透明傳遞到 Python，不得被吞掉。"""
        # 輸入一個違反 Formal Grammar 的字串
        raw_hallucination = "Hello world, I am a bot pretending to be a router."
        
        # 呼叫 Bridge
        res = self.core.normalize_intent(raw_hallucination)
        
        # 預期：返回 None (由 Bridge 轉換自 Rust 的 NormalizationError)
        # 且不應發生 Python 層的 Crash
        self.assertIsNone(res, "Rust error should be mapped to None in Bridge for safe handling.")

    def test_transition_matrix_closed_loop(self):
        """[Separation of Concerns] 驗證：Python 只能透過 Bridge 調用 TransitionEngine，無法繞過。"""
        # 合法轉移
        self.assertTrue(self.core.can_transition("PLAN", "EXECUTE"))
        # 非法轉移
        self.assertFalse(self.core.can_transition("PLAN", "VERIFY"))
        # 未知狀態 (Fail-Closed)
        self.assertFalse(self.core.can_transition("UNKNOWN", "PLAN"))

    def test_minimal_interface_leaks(self):
        """[Clean Code] 驗證：Bridge 不應暴露任何 Rust 內部的 struct 佈局或私有欄位。"""
        # 檢查 nexus_core 的屬性，應僅包含導出的函數
        attrs = dir(self.core)
        prohibited = ["FlowState", "TransitionGuard", "IntentNormalizer"] # 內部 struct 名稱
        for p in prohibited:
            self.assertNotIn(p, attrs, f"Internal struct {p} leaked through Bridge!")

if __name__ == "__main__":
    unittest.main()
