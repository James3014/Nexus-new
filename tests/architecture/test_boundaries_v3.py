import unittest
import ast
from pathlib import Path

class TestArchitectureBoundariesV3(unittest.TestCase):
    """
    [NEXUS v26.7] 物理邊界強化測試 (v5)
    核心原則：禁止逆向依賴，禁止橫向污染，允許合法的 Contract 引用。
    """
    
    def _check_illegal_imports(self, folder: str, forbidden: list[str]):
        paths = list(Path(folder).rglob("*.py"))
        for p in paths:
            code = p.read_text(encoding="utf-8")
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                    if module:
                        for f in forbidden:
                            if f in module:
                                # 排除 contract 引用 (合法的跨界)
                                if "contracts" in module:
                                    continue
                                self.fail(f"❌ ARCHITECTURE VIOLATION: {p} imports forbidden module '{module}'")

    def test_search_isolation(self):
        self._check_illegal_imports("nexus/search", ["nexus.selection", "nexus.verifiers", "nexus.feedback"])

    def test_feedback_isolation(self):
        # Feedback 負責映射訊號，不應依賴重試決策 internals
        self._check_illegal_imports("nexus/feedback", ["nexus.retry_policy"])

    def test_retry_policy_isolation(self):
        # Retry Policy 負責決策，不應反向依賴回饋映射細節
        self._check_illegal_imports("nexus/retry_policy", ["nexus.feedback.router"])

    def test_selection_isolation(self):
        self._check_illegal_imports("nexus/selection", ["nexus.search", "nexus.env", "nexus.feedback"])

    def test_controller_purity(self):
        # Controller 只准依賴各 Context 的 API (Router/Policy/Calibrator)
        self._check_illegal_imports("nexus/committee", ["nexus.verifiers.domain", "nexus.search.strategies"])

if __name__ == "__main__":
    unittest.main()
