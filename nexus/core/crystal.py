from pathlib import Path
import os
import json
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

class CrystalAnalyzer:
    """
    💎 Nexus v9 Crystal Analyzer
    主動掃描歷史軌跡，並將經驗結晶為權重修正值。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.tracelog_path = self.project_root / "tracelog.jsonl"
        self.weights_path = self.project_root / "scripts" / "core" / "autonomic_weights.json"
        self.adjustment_step = 0.2  # 權重修正步進值
        self.penalty_step = 0.5    # 懲罰步進值

    def analyze(self):
        logger.info("💎 [Crystal] Initiating experience crystallization...")
        if not self.tracelog_path.exists():
            logger.warning("⚠️ [Crystal] No tracelog found. Skipping.")
            return

        # 1. 讀取權重配置
        if not self.weights_path.exists():
            logger.error("❌ [Crystal] Weights config missing.")
            return
        
        with open(self.weights_path, "r", encoding="utf-8") as f:
            weights_data = json.load(f)

        adjustments = weights_data.get("skill_adjustments", {})
        
        # 2. 解析 Tracelog (僅分析最近 100 條)
        stats = defaultdict(lambda: {"success": 0, "fail": 0})
        with open(self.tracelog_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            recent_lines = lines[-100:]
            
            for line in recent_lines:
                try:
                    entry = json.loads(line)
                    # 嘗試從 task 或 command 提取關鍵字
                    task = entry.get("task", "").lower()
                    status = entry.get("status", "")
                    
                    # 比對已知的 skill 關鍵字
                    for skill_key in adjustments.keys():
                        if skill_key.lower() in task:
                            if status == "SUCCESS":
                                stats[skill_key]["success"] += 1
                            else:
                                stats[skill_key]["fail"] += 1
                except (KeyError, ValueError, TypeError) as e:
                    logger.debug("Crystal stat parse skip: %s", e)
                    continue

        # 3. 計算修正值
        changes_detected = False
        for skill_key, data in stats.items():
            net_change = (data["success"] * self.adjustment_step) - (data["fail"] * self.penalty_step)
            if net_change != 0:
                old_val = adjustments.get(skill_key, 0.0)
                new_val = round(old_val + net_change, 2)
                # 限制範圍 [-2.0, 5.0] 防止權重失控
                new_val = max(-2.0, min(5.0, new_val))
                
                if new_val != old_val:
                    logger.info(f"📈 [Crystal] Updating {skill_key}: {old_val} -> {new_val} (Success: {data['success']}, Fail: {data['fail']})")
                    adjustments[skill_key] = new_val
                    changes_detected = True

        # 4. 回寫配置
        if changes_detected:
            weights_data["skill_adjustments"] = adjustments
            weights_data["last_updated"] = datetime.now().isoformat()
            weights_data["total_sessions_analyzed"] += len(recent_lines)
            
            with open(self.weights_path, "w", encoding="utf-8") as f:
                json.dump(weights_data, f, indent=4, ensure_ascii=False)
            logger.info("✅ [Crystal] Weights successfully crystallized.")
        else:
            logger.info("ℹ️ [Crystal] No significant experience update needed.")

if __name__ == "__main__":
    _DEFAULT_ROOT = os.getenv("NEXUS_PROJECT_ROOT", "/Users/jameschen/Downloads/Muse-Nexus")
    analyzer = CrystalAnalyzer(_DEFAULT_ROOT)
    analyzer.analyze()
