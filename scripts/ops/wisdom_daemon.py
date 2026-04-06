# scripts/ops/wisdom_daemon.py
import time
import os
import sys
from pathlib import Path

# Ensure repo root is in path for imports
REPO_ROOT = Path(__file__).parents[2]
sys.path.append(str(REPO_ROOT))

# 🛡️ P8.3: Skip Protocol Gate for background efficiency
os.environ["NEXUS_SKIP_PROTOCOL_GATE"] = "1"

from nexus_swarm.healing.predictive_healer import PredictiveHealer

def main():
    print("🛡️ [Nexus Wisdom Daemon] Booting v23 Full Edition Closed-Loop...")
    healer = PredictiveHealer()
    
    print("✅ Daemon Active. Monitoring System Health (Interval: 30s)")
    try:
        while True:
            risk_res = healer.forecast_risk()
            
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            if risk_res['risk'] > 0.3:
                # Soft Alert
                status_color = "\033[93m[ALERT]\033[0m" if risk_res['risk'] < 0.7 else "\033[91m[CRITICAL]\033[0m"
                print(f"{ts} {status_color} Risk: {risk_res['risk']:.2f} | Actions: {risk_res['actions']}")
            else:
                # Healthy pulse
                print(f"{ts} [HEALTHY] Risk: {risk_res['risk']:.2f}", end="\r")
            
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n🛑 [Nexus Wisdom Daemon] Shutting down...")

if __name__ == "__main__":
    main()
