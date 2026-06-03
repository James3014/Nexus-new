import unittest
import ast
from pathlib import Path

class TestArchitectureBoundariesV4(unittest.TestCase):
    """
    [NEXUS v26.8] 物理邊界終極加固 (v6)
    核心原則：
    1. 單向依賴鏈：feedback -> retry_policy -> calibration -> abstention -> evaluation
    2. Orchestrator 隔離：Controller 僅調用公開介面，禁止滲透內部邏輯。
    3. Lane 隔離：Challenge 邏輯嚴禁滲透至 Baseline 車道。
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
                                # 允許合法的 contracts 引用
                                if "contracts" in module or "models" in module:
                                    continue
                                self.fail(f"❌ ARCHITECTURE VIOLATION in {p}: Forbidden module '{module}' imported.")

    def test_dependency_chain_purity(self):
        # 1. Feedback 不應依賴後續決策
        self._check_illegal_imports("nexus/feedback", ["nexus.retry_policy", "nexus.abstention"])
        
        # 2. Retry Policy 不應依賴 Feedback 的 Mapping 實作
        self._check_illegal_imports("nexus/retry_policy", ["nexus.feedback.router"])
        
        # 3. Calibration 保持數學純淨
        self._check_illegal_imports("nexus/calibration", ["nexus.verifiers.packs", "nexus.selection", "nexus.abstention"])
        
        # 4. Abstention 僅准依賴校準結果
        self._check_illegal_imports("nexus/abstention", ["nexus.verifiers.domain", "nexus.search"])

    def test_lane_isolation(self):
        # Baseline 不得引用 Challenge 相關邏輯
        self._check_illegal_imports("nexus/evaluation/baseline_lane", ["nexus.evaluation.challenge_lane"])

    def test_controller_thinness(self):
        # Controller 不應涉及具體的策略細節
        self._check_illegal_imports("nexus/committee", ["nexus.verifiers.domain", "nexus.search.strategies"])

if __name__ == "__main__":
    unittest.main()
