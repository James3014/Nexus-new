import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ReflexLoop:
    """
    🧬 ReflexLoop (Layer 4 Background Self-Optimization)
    職責: 作為系統神經反射中樞，定期整合 MetricsAggregator 的數據並對各子模組
    (如 NAS Tuner, BattleSwarm) 進行超參數優化。
    """
    def __init__(self, project_root: str, memory_service=None):
        self.project_root = Path(project_root).resolve()
        self.memory = memory_service
        self.log_path = self.project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
        self.config_path = self.project_root / ".nexus" / "config" / "reflex_params.json"
        self._ensure_config()

    def _ensure_config(self):
        """確保配置存在。"""
        if not self.config_path.parent.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            default_config = {
                "battle_workers": 4,
                "battle_budget_minutes": 3,
                "ash_retry_limit": 3
            }
            self.config_path.write_text(json.dumps(default_config, indent=2))

    @property
    def config(self) -> Dict[str, Any]:
        try:
            return json.loads(self.config_path.read_text())
        except Exception:
            return {"battle_workers": 4, "battle_budget_minutes": 3, "ash_retry_limit": 3}

    def _save_config(self, config: Dict[str, Any]):
        self.config_path.write_text(json.dumps(config, indent=2))

    def evaluate_battle_swarm_performance(self, limit: int = 50) -> Dict[str, Any]:
        """讀取近期結果，動態評估 BattleSwarm 性能並調整 workers / budget。"""
        if not self.log_path.exists():
            return {"updated": False, "reason": "No log file"}
            
        history = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
                for line in lines:
                    data = json.loads(line)
                    meta = data.get("metadata", {})
                    # 確認是否經歷過 BattleSwarm，我們檢查特徵標記
                    if "battle_swarm_triggered" in meta or data.get("skill_id", "").startswith("battle-"):
                        # 'passed' in payload
                        history.append({"pass": data.get("passed", False)})
        except Exception as e:
            return {"updated": False, "reason": str(e)}

        if not history:
            return {"updated": False, "reason": "No BattleSwarm history"}

        current_config = self.config
        current_workers = current_config.get("battle_workers", 4)
        
        passes = sum(1 for h in history if h["pass"])
        success_rate = passes / len(history)

        adjustment = False
        # 如果最近在 BattleSwarm 模式下成功率過低 (< 20%)，我們加強試錯力
        if success_rate < 0.2 and current_workers < 8:
            current_config["battle_workers"] = min(current_workers + 1, 8)
            adjustment = True
            logger.info(f"🧬 [ReflexLoop] Low swarm success rate ({success_rate:.0%}). Increasing battle_workers to {current_config['battle_workers']}.")
        
        # 如果成功率極高 (> 80%)，我們可以省點力氣，降級 workers 節省資源
        elif success_rate > 0.8 and current_workers > 2:
            current_config["battle_workers"] = current_workers - 1
            adjustment = True
            logger.info(f"🧬 [ReflexLoop] High swarm success rate ({success_rate:.0%}). Decreasing battle_workers to {current_config['battle_workers']} to save compute.")

        if adjustment:
            self._save_config(current_config)
            return {"updated": True, "new_workers": current_config["battle_workers"], "old_workers": current_workers}

        return {"updated": False}

    def run_cycle(self) -> Dict[str, Any]:
        """
        執行一次背景反射神經週期。
        - 包含 RouterNAS 更新
        - 包含 BattleSwarm 參數更新
        """
        logger.info("🧬 [ReflexLoop] Initiating background optimization cycle...")
        changes = {}
        
        # 1. 路由閥值演化
        try:
            from nexus.learning.router_nas_tuner import RouterNASTuner
            tuner = RouterNASTuner(str(self.project_root), self.memory)
            nas_res = tuner.auto_tune_from_log()
            if nas_res.get("updated"):
                changes["router_nas"] = nas_res
                logger.info(f"🧬 [NAS] Threshold Evolved: {nas_res.get('old')} -> {nas_res.get('new')}")
        except Exception as e:
             logger.warning(f"⚠️ [ReflexLoop] NAS Tuner cycle failed: {e}")

        # 2. BattleSwarm 參數演化
        try:
            swarm_res = self.evaluate_battle_swarm_performance()
            if swarm_res.get("updated"):
                changes["battle_swarm"] = swarm_res
        except Exception as e:
             logger.warning(f"⚠️ [ReflexLoop] BattleSwarm tune cycle failed: {e}")

        logger.info(f"🧬 [ReflexLoop] Cycle complete. Components updated: {list(changes.keys())}")
        return changes
