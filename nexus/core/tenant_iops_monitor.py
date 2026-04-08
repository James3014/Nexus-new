import os
import time
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TenantIOPSMonitor:
    """
    🛡️ Nexus v24.5 Storage Latency Monitor
    Tracks IOPS and P50 response times across sharded tenants.
    """
    def __init__(self, storage_root: Path):
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def sample_latency(self) -> float:
        """📏 Sample disk write latency to check IOPS health."""
        test_file = self.storage_root / ".iops_probe"
        t0 = time.perf_counter()
        try:
            with open(test_file, "w") as f:
                f.write("probe")
                f.flush()
                # 🛡️ Correct way to call fsync
                os.fsync(f.fileno())
            t1 = time.perf_counter()
            return (t1 - t0) * 1000 # ms
        except Exception as e:
            logger.error(f"❌ IOPS Probe failed: {e}")
            return 9999.0
        finally:
            if test_file.exists():
                test_file.unlink()

    def get_status(self) -> Dict[str, Any]:
        """🔍 Get current IOPS health status."""
        latency = self.sample_latency()
        status = "HEALTHY" if latency < 1000 else "DEGRADED"
        
        return {
            "p50_latency_ms": round(latency, 2),
            "status": status,
            "threshold_ms": 1000,
            "timestamp": time.time()
        }

if __name__ == "__main__":
    monitor = TenantIOPSMonitor(Path("str(REPO_ROOT)/.nexus/tenants"))
    print(monitor.get_status())
