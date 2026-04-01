#!/usr/bin/env python3
import os
import logging
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class ASHStrategy:
    """🛡️ ASH 自癒策略定義：包含識別碼、成功權重與指令模板引用 (Command Refs)。"""
    id: str
    success_base: float
    commands: List[str] = field(default_factory=list) # 語義升級：指令引用列表其內容及對度內容。

@dataclass
class ASHMatrix:
    """🌐 ASH 自癒指令矩陣內容性能。"""
    strategies: Dict[str, ASHStrategy] = field(default_factory=dict)

    def get_ranked_strategies(self) -> List[ASHStrategy]:
        """按 ID 或其他預設順序獲取所有策略內容分析。"""
        return list(self.strategies.values())

    @staticmethod
    def default() -> "ASHMatrix":
        """獲取內建基準矩陣其性質內容及對等。"""
        return ASHMatrix(strategies={
            "direct_fix": ASHStrategy("direct_fix", 0.5, ["patch"]),
            "research_first": ASHStrategy("research_first", 0.7, ["search", "patch"]),
            "replan_swarm": ASHStrategy("replan_swarm", 0.8, ["replan", "execute"])
        })

class ASHMatrixLoader:
    """📂 ASH 矩陣載入器：支援環境覆寫與物理層級合併內容性能及對度。"""
    
    @staticmethod
    def load(project_root: str, env: str = "dev") -> ASHMatrix:
        matrix_path = Path(project_root) / ".nexus" / "ash_matrix.yaml"
        
        if not matrix_path.exists():
            logger.warning("⚠️ [ASHLoader] Missing %s, using defaults.", matrix_path)
            matrix = ASHMatrix.default()
        else:
            try:
                with open(matrix_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                
                # 1. 獲取基準策略 (Default Strategies)
                base_data = data.get("default", {}).get("strategies", {})
                # 2. 獲取環境覆寫 (Env Overrides)
                env_overrides = data.get("environments", {}).get(env, {})
                
                strategies = {}
                # 3. 物理合併策略內容及對等分析。
                all_ids = set(base_data.keys()) | set(env_overrides.keys())
                for s_id in all_ids:
                    s_base = base_data.get(s_id, {})
                    s_env = env_overrides.get(s_id, {})
                    
                    # 合併欄位內容及性能分析。
                    mapped_strat = ASHStrategy(
                        id=s_id,
                        success_base=s_env.get("success_base", s_base.get("success_base", 0.5)),
                        commands=s_env.get("commands", s_base.get("commands", ["unknown"]))
                    )
                    strategies[s_id] = mapped_strat
                
                matrix = ASHMatrix(strategies=strategies)
                logger.info("📡 [ASHLoader] Matrix loaded for env [%s] with %d strategies.", env, len(strategies))
                
            except Exception as e:
                logger.error("❌ [ASHLoader] Failed to load matrix: %s", e)
                matrix = ASHMatrix.default()
        
        return matrix
