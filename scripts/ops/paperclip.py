import logging
import os
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class PaperclipDaemon:
    """🛸 [Wave 1] Agent Heartbeat & RBAC Eviction (Standard Library Edition)"""

    def __init__(self, watch_dir: Path):
        self.watch_dir = watch_dir
        self.watch_dir.mkdir(parents=True, exist_ok=True)

    def scan_once(self) -> dict:
        """Return one deterministic, read-only heartbeat snapshot."""
        entries = []
        for heartbeat in sorted(self.watch_dir.glob("*.hb"), key=lambda path: path.name):
            try:
                pid = int(heartbeat.stem)
            except ValueError:
                pid = None
            valid = pid is not None and pid > 0
            entries.append({"name": heartbeat.name, "pid": pid, "valid": valid})
        invalid_count = sum(not entry["valid"] for entry in entries)
        return {
            "schema": "nexus.paperclip_heartbeat_snapshot.v1",
            "watch_dir": str(self.watch_dir.resolve()),
            "entries": entries,
            "valid_count": len(entries) - invalid_count,
            "invalid_count": invalid_count,
            "status": "OK" if invalid_count == 0 else "INVALID_ENTRIES",
        }

    def monitor(self):
        logger.info("🛸 [Paperclip] Starting agent heartbeat monitor (No-Dep)...")
        while True:
            for hb_file in self.watch_dir.glob("*.hb"):
                try:
                    pid = int(hb_file.stem)
                    # 🚀 行動 4: 偵測死亡或違規 (使用 os.kill(pid, 0) 檢查存活)
                    if not self._pid_exists(pid) or self._is_rbac_violated(pid):
                        logger.warning(f"🛸 [Paperclip] EVICTING ZOMBIE/VIOLATOR PID: {pid}")
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        hb_file.unlink()
                except (ValueError, OSError):
                    pass
            time.sleep(5)

    def _pid_exists(self, pid: int) -> bool:
        """使用標準庫檢查進程是否存在"""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # 存在但無權限操作，視為存活
        else:
            return True

    def _is_rbac_violated(self, pid) -> bool:
        return False


if __name__ == "__main__":
    daemon = PaperclipDaemon(Path(".nexus/heartbeats"))
    daemon.monitor()
