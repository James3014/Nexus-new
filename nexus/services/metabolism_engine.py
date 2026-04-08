import os
import json
import logging
from typing import Dict, Any
from nexus.core.p_loop_manager import PPhase

logger = logging.getLogger(__name__)

class SessionMetabolism:
    """🛡️ Nexus v25.5 Session Metabolism Engine."""
    def __init__(self, token_limit: int = 128000):
        self.token_limit = token_limit
        self.threshold = 0.85
        self.last_aaak_ratio = 1.0

    def should_distill(self, current_tokens: int) -> bool:
        """🔍 Check if session needs distillation."""
        ratio = current_tokens / self.token_limit
        if ratio >= self.threshold:
            logger.warning(f"⚠️ [Metabolism:REACHED] Token usage {current_tokens} ({ratio:.2%}) triggers distillation.")
            return True
        return False

    def distill(self, session_essence: Dict[str, Any], p_manager: Any = None) -> str:
        """📉 Snapshots context and uploads to Arweave."""
        logger.info("🧪 [Metabolism:DISTILLING] (P4) Extracting core intent and context...")
        
        # [Phase 36.5 Alignment] Update P-Loop state to P4
        if p_manager:
            p_manager.transition_to(PPhase.P4_METABOLIZE, {"trigger": "token_pressure", "limit": self.token_limit})
        
        # 🔗 Mock Arweave upload in development
        arweave_tx = f"ar_tx_distilled_{int(os.path.getmtime(__file__))}"
        
        # Save locally as golden source reference
        lineage_path = "str(REPO_ROOT)/.nexus/eternal/lineage.json"
        os.makedirs(os.path.dirname(lineage_path), exist_ok=True)
        
        history = []
        if os.path.exists(lineage_path):
            with open(lineage_path, 'r') as f:
                history = json.load(f)
        
        history.append({
            "tx_id": arweave_tx,
            "essence": session_essence,
            "timestamp": "now"
        })
        
        with open(lineage_path, 'w') as f:
            json.dump(history, f, indent=2)
            
        logger.info(f"✅ [Metabolism:SAVED] Golden Source anchored: {arweave_tx}")
        return arweave_tx

# Global Metabolism Service
metabolism = SessionMetabolism()
