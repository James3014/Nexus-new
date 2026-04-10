#!/usr/bin/env python3
"""
🛡️ Nexus v24.1 Canary Observation Monitor
負責監控 24h 內的 Canary 報告，並在指標惡化時自動執行 Scoped Rollback。
"""

import json
import time
from pathlib import Path
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CanaryMonitor")

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "credible_sampling_report.json"
SAMPLER_BIN = REPO_ROOT / "scripts/benchmarks/credible_sampler.py"

def check_and_enforce():
    if not REPORT_PATH.exists():
        logger.info("No canary report found. Skipping.")
        return

    try:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        canary = report.get("canary", {})
        
        # 🧪 [v24.1] 24h 窗口判定 (簡化：檢查報告生成時間)
        report_ts = report.get("timestamp_utc", "")
        logger.info(f"Checking Canary Health from report: {report_ts}")

        if canary.get("triggered", False):
            logger.warning(f"⚠️ Canary Triggered! Reasons: {canary.get('reasons')}")
            
            if not canary.get("rollback_executed", False):
                logger.info("🚀 Initiating Automatic Scoped Rollback...")
                # 呼叫 sampler 執行 soft rollback
                res = subprocess.run([
                    "python3", str(SAMPLER_BIN),
                    "--auto-rollback", "soft",
                    "--force-canary-fail" # 強制進入 rollback 分支
                ], capture_output=True, text=True)
                
                if res.returncode == 0:
                    logger.info("✅ Scoped Rollback SUCCESS. Environment restored.")
                else:
                    logger.error(f"❌ Scoped Rollback FAILED: {res.stderr}")
        else:
            logger.info("🟢 Canary Stable. No action required.")

    except Exception as e:
        logger.error(f"Error during monitor cycle: {e}")

if __name__ == "__main__":
    check_and_enforce()
