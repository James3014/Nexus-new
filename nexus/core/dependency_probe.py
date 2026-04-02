from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import ast
import logging

logger = logging.getLogger(__name__)

class DependencyProbe:
    """
    🔍 Nexus 依賴圖探針 (AOS-P5.2)
    自動掃描物理依賴網絡，並識別高風險修改目標。
    """
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self._index: Dict[str, List[str]] = {}  # file_path -> imported_modules

    def build_index(self):
        """🔍 遍歷工作區並建立索引"""
        logger.info("📡 [DepProbe] Building dependency index for %s...", self.workspace.name)
        for py_file in self.workspace.rglob("*.py"):
            if ".venv" in str(py_file) or ".nexus" in str(py_file):
                continue
            relative_path = str(py_file.relative_to(self.workspace))
            self._index[relative_path] = self._extract_imports(py_file)

    def _extract_imports(self, file_path: Path) -> List[str]:
        """從單個檔案提取進口模組"""
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        imports.append(n.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            return list(set(imports))
        except Exception as e:
            logger.debug(f"⚠️ [DepProbe] Failed to parse {file_path}: {e}")
            return []

    def _file_to_module(self, file_path: str) -> str:
        """將路徑轉換為模組名格式 (e.g. nexus/core/swarm.py -> nexus.core.swarm)"""
        return file_path.replace("/", ".").replace(".py", "")

    def who_imports(self, target_file: str) -> List[str]:
        """誰直接 import 了這個檔案的代表模組"""
        module_name = self._file_to_module(target_file)
        # 搜尋索引中的模組名匹配
        dependents = []
        for file, imports in self._index.items():
            if any(module_name in imp for imp in imports):
                dependents.append(file)
        return dependents

    def full_impact(self, target_file: str) -> Dict[str, Any]:
        """計算全量影響範圍與風險等級"""
        direct = self.who_imports(target_file)
        
        # 二層感應：間接依賴
        indirect = set()
        for d in direct:
            indirect.update(self.who_imports(d))
            
        # 排除自體迴圈
        if target_file in indirect:
            indirect.remove(target_file)
            
        risk_level = "LOW"
        if len(direct) > 5:
            risk_level = "HIGH"
        elif direct:
            risk_level = "MEDIUM"
            
        return {
            "target": target_file,
            "direct_dependents": direct,
            "indirect_dependents": list(indirect),
            "risk_level": risk_level,
            "impact_count": len(direct) + len(indirect)
        }
