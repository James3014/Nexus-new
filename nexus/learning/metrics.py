import ast
import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Set

logger = logging.getLogger(__name__)

@dataclass
class CodeMetrics:
    line_count: int
    complexity: int
    coupling: int
    method_count: int
    srp_violation: bool

class MetricsAnalyzer:
    """🌐 Nexus v22-Linus Code Metrics Analyzer
    
    使用 AST 對物理代碼進行靜態掃描，計算圈複雜度與耦合度。
    數據真值轉向 Nexus Style 治理層。
    """
    
    def analyze_file(self, file_path: str) -> CodeMetrics:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        tree = ast.parse(content)
        lines = content.splitlines()
        
        complexity = self._calculate_complexity(tree)
        coupling = self._calculate_coupling(tree)
        methods = self._get_method_count(tree)
        
        # 🛡️ 物理規則：方法 > 10 或 行數 > 300 視為 SRP 潛在違規
        srp_violation = methods > 10 or len(lines) > 300 or complexity > 15
        
        metrics = CodeMetrics(
            line_count=len(lines),
            complexity=complexity,
            coupling=coupling,
            method_count=methods,
            srp_violation=srp_violation
        )
        
        logger.info("metrics_analyzed [%s] complexity=%d coupling=%d srp=%s", 
                    file_path, complexity, coupling, srp_violation)
        return metrics

    def _calculate_complexity(self, tree: ast.AST) -> int:
        """計算圈複雜度 (Cyclomatic Complexity)。基於分支節點。"""
        count = 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor, 
                                ast.And, ast.Or, ast.ExceptHandler)):
                count += 1
        return count

    def _calculate_coupling(self, tree: ast.AST) -> int:
        """分析模組耦合度 (Coupling)。基於外部 Import 與 呼叫鏈。"""
        external_refs: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # 統計 Import 數量
                for alias in node.names:
                    external_refs.add(alias.name)
            elif isinstance(node, ast.Attribute):
                # 統計跨模組呼叫 (例如 os.path.exists)
                if isinstance(node.value, ast.Name):
                    external_refs.add(node.value.id)
        return len(external_refs)

    def _get_method_count(self, tree: ast.AST) -> int:
        """統計頂層與類別內的方法數量。"""
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count += 1
        return count
