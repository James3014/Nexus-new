from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import logging
import re
from nexus.core.state_contracts import NexusState

import json
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ExecutionPlan:
    mode: str          # "standard" | "swarm" | "research_first" | "self_heal"
    reason: str        # 決策原因
    confidence: float  # 0.0 - 1.0

class AutonomicRouter:
    """
    🧠 Nexus Autonomic Router (v24.3)
    職責: 根據任務特徵、歷史記憶與物理限制，自動決定執行策略。
    """
    DEFAULT_CONFIG = {
        "token_threshold": 8000,
        "retry_threshold": 3,
        "research_keywords": [r"research", r"unknown", r"learn", r"學術", r"研究"],
        "self_heal_threshold": 0.8
    }

    def __init__(self, project_root: str = ".", memory_service=None, config: Optional[Dict] = None):
        self.project_root = Path(project_root).resolve()
        self.memory = memory_service
        self.config_path = self.project_root / ".nexus" / "config" / "router_nas.json"
        
        if config:
            self.config = config
        else:
            self.config = self._load_config()

    def _load_config(self) -> Dict:
        """從實體檔案讀取閾值，若無則初始化"""
        if not self.config_path.exists():
            self._save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"⚠️ [Router:Config] Load failed: {e}. Using defaults.")
            return self.DEFAULT_CONFIG

    def _save_config(self, config: Dict):
        """將閾值寫入實體檔案"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"❌ [Router:Config] Save failed: {e}")

    def route(self, task_desc: str, state: NexusState, forecast: Dict[str, Any], pre_routing: Optional[Dict] = None) -> ExecutionPlan:
        """主動路由決策矩陣"""
        pre_routing = pre_routing or {}
        
        # 1. 檢查歷史故障模式 (Self-Heal Priority)
        # ... (rest of logic)
        # 如果 MemoryService 命中強大的故障教訓，優先考慮自癒模式
        if self.memory:
            fault_lessons = self.memory.lookup_fault_lessons(state.task_id[:8]) # 模擬 hash
            if fault_lessons and len(fault_lessons) > 0:
                return ExecutionPlan(
                    mode="self_heal",
                    reason="Memory Match: Found existing fault lessons for similar patterns.",
                    confidence=0.9
                )

        # 2. 檢查重試次數 (Escalation to Swarm)
        # 如果單機模式已失敗多次，強制升級為蜂群進行並行探索
        retry_count = state.audit.retry_count if hasattr(state, "audit") else 0
        if retry_count >= self.config["retry_threshold"]:
            return ExecutionPlan(
                mode="swarm",
                reason=f"Escalation: Retry count ({retry_count}) exceeded threshold ({self.config['retry_threshold']}).",
                confidence=1.0
            )

        # 3. 檢查預估 Token (Compute Intensity)
        est_tokens = forecast.get("est_tokens", 0)
        if est_tokens is None:
            est_tokens = 0
            
        if est_tokens > self.config["token_threshold"]:
            return ExecutionPlan(
                mode="swarm",
                reason=f"Complexity: Estimated tokens ({est_tokens}) exceeds density threshold ({self.config['token_threshold']}).",
                confidence=0.85
            )

        # 4. 關鍵詞感應 (Intent Recognition)
        desc_lower = task_desc.lower()
        if any(re.search(kw, desc_lower) for kw in self.config["research_keywords"]):
            return ExecutionPlan(
                mode="research_first",
                reason="Intent: Task description indicates academic or deep-research requirement.",
                confidence=0.95
            )

        # 5. 預設路由
        return ExecutionPlan(
            mode="standard",
            reason="Classification: Standard task complexity within single-agent bounds.",
            confidence=1.0
        )
