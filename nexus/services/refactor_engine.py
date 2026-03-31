import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from nexus.learning.metrics import MetricsAnalyzer, CodeMetrics

logger = logging.getLogger(__name__)

class RefactorEngine:
    """🌐 Nexus v22-Linus Refactor Engine
    
    負責執行「漸進式重構」策略。
    基於 Code Metrics 自動排布優先級 DAG 並執行「Linus 小步提交」。
    數據真值轉向 Nexus Style 治理層。
    """
    
    def __init__(self, project_root: Path):
        self.root = project_root
        self.analyzer = MetricsAnalyzer()

    def generate_plan(self, task: str, target_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """產出優先級重構清單 (Progressive List)。"""
        scan_dir = Path(target_dir) if target_dir else self.root
        
        # 1. 物理掃描高危組件
        candidates = []
        for py_file in scan_dir.glob("**/*.py"):
            try:
                metrics = self.analyzer.analyze_file(str(py_file))
                if metrics.srp_violation or metrics.complexity > 10:
                    candidates.append({
                        "id": str(py_file.relative_to(self.root)),
                        "path": str(py_file),
                        "metrics": metrics
                    })
            except: continue
            
        # 2. 按優先級排序 (複雜度 * 耦合度 權重)
        candidates.sort(key=lambda x: x["metrics"].complexity * x["metrics"].coupling, reverse=True)
        
        # 3. 具現化 DAG 任務
        plan = []
        for idx, cand in enumerate(candidates[:8]):
            priority = f"P{idx+1}"
            plan.append({
                "priority": priority,
                "file": cand["id"],
                "task": f"Refactor {cand['id']}: Fix SRP & Reduce Complexity ({cand['metrics'].complexity})",
                "rules": ["linus-mode", "small-commit", "coverage-95"]
            })
            
        logger.info("refactor_plan_generated_progressive_list [%d_nodes]", len(plan))
        return plan

    def execute_linus_step(self, task_id: str, code_diff: str) -> bool:
        """執行「Linus 小步提交」物理攔截。"""
        # 🛡️ 物理規則：一次提交不得超過 100 行
        lines_changed = len(code_diff.splitlines())
        if lines_changed > 100:
            logger.warning("linus_mode_block_excessive_diff [%d_lines]", lines_changed)
            return False
        
        # 此處應配合 git 執行小步提交
        logger.info("linus_mode_step_approved [%d_lines]", lines_changed)
        return True
