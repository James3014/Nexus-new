from pathlib import Path
#!/usr/bin/env python3
import os
import logging
from nexus.core.gate_evaluator import AcceptancePolicy

logger = logging.getLogger(__name__)

class PolicyLoader:
    """
    📂 政策載入器 (PolicyLoader)
    負責從 .nexus/governance_policy.yaml 物理載入治理門檻內容性能及性能。
    落實指揮官「保守外部化」原則內容性能。內容及性能。內容性能。性能分析。
    """
    
    @staticmethod
    def load(project_root: str, env: str = "dev") -> AcceptancePolicy:
        """
        🔗 層級式載入 (Hierarchical Load):
        1. 物理路徑: .nexus/governance_policy.yaml
        2. 讀取 [default] 區塊基準。
        3. 根據環境 (env) 讀取 [environments] 區塊覆寫。
        4. 物理合併 [gates] 與 [health] 子區塊內容。
        """
        policy_path = Path(project_root) / ".nexus" / "governance_policy.yaml"
        
        if not policy_path.exists():
            logger.warning("⚠️ [PolicyLoader] Missing %s, using defaults (Env: %s)", policy_path, env)
            return AcceptancePolicy.default()
            
        try:
            import yaml
            with open(policy_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
            # 1. 獲取基準配置 (Base)
            base = data.get("default", {})
            # 2. 獲取環境特定配置 (Env Override)
            env_data = data.get("environments", {}).get(env, {})
            
            # 3. 執行細粒度合併 (Deep Merge for sub-blocks)
            merged_payload = {
                "gates": {**base.get("gates", {}), **env_data.get("gates", {})},
                "health": {**base.get("health", {}), **env_data.get("health", {})}
            }
            
            logger.info("📡 [PolicyLoader] Env [%s] loaded with layered overrides.", env)
            return AcceptancePolicy.from_dict(merged_payload)
                
        except Exception as e:
            logger.error("❌ [PolicyLoader] Failed to parse policy (Env: %s): %s", env, e)
            return AcceptancePolicy.default()
