import time
import logging
from pathlib import Path
from scripts.ops.predictive_healing import PredictiveHealingEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HealingDaemon")

def run_daemon():
    root = Path(__import__("pathlib").Path(__file__).resolve().parents[2])
    engine = PredictiveHealingEngine(root)
    
    logger.info("🛡️ Nexus Predictive Healing Daemon STARTED (v0.4)")
    
    try:
        while True:
            logger.info("🔍 [Daemon] Initiating scheduled risk scan...")
            risks = engine.predict_risks()
            
            if risks:
                logger.info(f"⚠️ [Daemon] Found {len(risks)} at-risk artifacts. Starting healing sequence...")
                proposals = engine.heal_artifacts(risks)
                traces = engine.validate_proposals(proposals)
                
                pass_count = sum(1 for t in traces if t["status"] == "PASS")
                logger.info(f"✅ [Daemon] Healing sequence complete. {pass_count}/{len(traces)} passed validation.")
            else:
                logger.info("🟢 [Daemon] No risks detected. System healthy.")
            
            # 模擬定時掃描 (測試時縮短為 30 秒)
            logger.info("😴 [Daemon] Sleeping for 30s...")
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("🛑 [Daemon] Shutting down...")

if __name__ == "__main__":
    run_daemon()
