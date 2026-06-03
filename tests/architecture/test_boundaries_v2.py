import unittest
import ast
from pathlib import Path

class TestArchitectureBoundariesV2(unittest.TestCase):
    """
    [Task T15] 物理鎖定五個 Bounded Contexts。
    核心原則：禁止 Controller 直接接觸實作細節，禁止逆向依賴。
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
                                self.fail(f"❌ ARCHITECTURE VIOLATION: {p} imports forbidden module '{module}'")

    def test_search_context_isolation(self):
        # Search 應該是獨立的生成器，不應依賴 Selection 或 Verifiers
        self._check_illegal_imports("nexus/search", ["nexus.selection", "nexus.verifiers"])

    def test_selection_context_purity(self):
        # Selection 只負責決策政策，不應依賴 Search 的採樣細節
        self._check_illegal_imports("nexus/selection", ["nexus.search", "nexus.env"])

    def test_controller_dependency_direction(self):
        # Controller 作為 Orchestrator，應依賴各 Context 的 API，但不應依賴具體的 Domain 實作
        self._check_illegal_imports("nexus/committee", ["nexus.verifiers.domain"])

if __name__ == "__main__":
    unittest.main()
