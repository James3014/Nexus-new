import unittest
import ast
from pathlib import Path

class TestArchitectureBoundaries(unittest.TestCase):
    """
    [NEXUS v26.4] Architecture Boundary Tests (T12)
    保證 Bounded Contexts 之間不發生逆向依賴或跨層污染。
    """
    
    def _check_imports(self, file_path: str, forbidden_patterns: list[str]):
        path = Path(file_path)
        if not path.exists():
            return
            
        code = path.read_text(encoding="utf-8")
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            # 檢查 from ... import ...
            if isinstance(node, ast.ImportFrom) and node.module:
                for pattern in forbidden_patterns:
                    if pattern in node.module:
                        self.fail(f"Architecture Violation in {file_path}: Illegal import '{node.module}' matches forbidden '{pattern}'")
            # 檢查 import ...
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for pattern in forbidden_patterns:
                        if pattern in alias.name:
                            self.fail(f"Architecture Violation in {file_path}: Illegal import '{alias.name}' matches forbidden '{pattern}'")

    def test_controller_does_not_import_domain_verifiers(self):
        """
        驗證：Controller 不應直接依賴具體的 Domain Verifiers。
        它只能與 VerifierRegistry 互動。
        """
        self._check_imports(
            "nexus/committee/controller.py",
            forbidden_patterns=["verifiers.domain"]
        )

    def test_env_does_not_depend_on_committee(self):
        """
        驗證：Environment 模組不應反向依賴 Committee 選優邏輯。
        """
        env_files = list(Path("nexus/services/local_heal").rglob("env_*.py"))
        for f in env_files:
            self._check_imports(str(f), forbidden_patterns=["nexus.committee"])

if __name__ == "__main__":
    unittest.main()
