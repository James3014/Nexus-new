import unittest
import ast
from pathlib import Path

class TestArchitectureBoundariesV2(unittest.TestCase):
    """
    [Task T17] 物理鎖定 v26.6 五大 Bounded Contexts。
    核心原則：禁止逆向依賴，禁止橫向污染 (Cali vs Packs)。
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
        self._check_illegal_imports("nexus/search", ["nexus.selection", "nexus.verifiers"])

    def test_selection_context_purity(self):
        self._check_illegal_imports("nexus/selection", ["nexus.search", "nexus.env"])

    def test_calibration_context_isolation(self):
        # Calibration 應為純淨的數學校準層，不應依賴領域外掛或決策政策
        self._check_illegal_imports("nexus/calibration", ["nexus.verifiers.packs", "nexus.selection"])

    def test_packs_context_isolation(self):
        # Packs 應為純淨的領域邏輯，不應依賴全域選優政策
        self._check_illegal_imports("nexus/verifiers/packs", ["nexus.selection"])

    def test_controller_dependency_direction(self):
        # Controller 不應依賴具體的 Domain 實作
        self._check_illegal_imports("nexus/committee", ["nexus.verifiers.domain"])

if __name__ == "__main__":
    unittest.main()
