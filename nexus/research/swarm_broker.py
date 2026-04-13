import os
import shutil
import logging
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

class SwarmBroker:
    """
    🐝 蜂群空間調度器 (Swarm Workspace Broker)
    管理實體 `.nexus-swarm-*` 目錄的租用、同步與釋放。
    提供真正的物理隔離平行測試環境，消滅高並行競爭。
    """
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        # Find all available swarm directories (e.g., .nexus-swarm-001 to 050)
        self.swarm_dirs = sorted([d for d in self.workspace.glob(".nexus-swarm-*") if d.is_dir()])
        if not self.swarm_dirs:
            logger.warning("⚠️ [SwarmBroker] No .nexus-swarm-* directories found. Parallel isolation may be degraded.")

    def acquire(self, timeout_sec: float = 60.0) -> Optional[Path]:
        """
        租用一個閒置的 Swarm 目錄。支援跨進程的原子鎖定。
        """
        if not self.swarm_dirs:
            return None

        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            for swarm_dir in self.swarm_dirs:
                lock_file = swarm_dir / ".swarm_lock"
                try:
                    # Attempt to create the lock file exclusively for cross-process safety
                    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    logger.debug(f"🐝 [SwarmBroker] Acquired swarm sandbox: {swarm_dir.name}")
                    return swarm_dir
                except FileExistsError:
                    continue  # Already locked by another process/thread
            time.sleep(0.5)
        
        logger.error("❌ [SwarmBroker] Timeout waiting for an available Swarm directory.")
        return None

    def sync_scope(self, swarm_dir: Path, scope_files: List[str], required_configs: List[str] = None):
        """
        將主工作區的 Scope 檔案與設定檔同步至 Swarm 目錄中。
        """
        if not required_configs:
            # Sync essential configuration files so testing works normally in the isolated dir
            required_configs = [
                "pytest.ini", 
                "pyproject.toml", 
                "uv.lock", 
                "tests/conftest.py"
            ]
            
        all_paths = list(scope_files) + required_configs
        
        for rel_path in all_paths:
            src = self.workspace / rel_path
            dst = swarm_dir / rel_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

    def release(self, swarm_dir: Path):
        """
        清空 Swarm 目錄內容（還原為初始狀態）並解除鎖定。
        """
        if not swarm_dir or not swarm_dir.exists():
            return
            
        lock_file = swarm_dir / ".swarm_lock"
        try:
            # Clean up all contents EXCEPT the lock file
            for item in swarm_dir.iterdir():
                if item.name == ".swarm_lock":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            
            # Finally remove the lock file to release it back to the pool
            if lock_file.exists():
                lock_file.unlink()
            logger.debug(f"🐝 [SwarmBroker] Released and cleaned swarm sandbox: {swarm_dir.name}")
        except Exception as e:
            logger.error(f"❌ [SwarmBroker] Error releasing swarm {swarm_dir.name}: {e}")
