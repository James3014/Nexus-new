import os
import shutil
import logging
import time
import subprocess
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

    def _git_output(self, args: List[str], cwd: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    def _git_top_level(self, path: Path) -> Optional[Path]:
        output = self._git_output(["rev-parse", "--show-toplevel"], path)
        if not output:
            return None
        return Path(output).resolve()

    def _controller_git_top_level(self) -> Optional[Path]:
        return self._git_top_level(self.workspace)

    def _registered_worktree_paths(self) -> set[Path]:
        output = self._git_output(["worktree", "list", "--porcelain"], self.workspace)
        if output is None:
            return set()

        paths: set[Path] = set()
        for line in output.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree" and value:
                paths.add(Path(value).resolve())
        return paths

    def is_independently_registered_worktree(self, swarm_dir: Path) -> bool:
        """
        Validate that a swarm path is a separate Git worktree registered by the
        controller, not a normal child directory that resolves back to it.
        """
        swarm_path = Path(swarm_dir).resolve()
        if not swarm_path.is_dir():
            return False
        controller_top_level = self._controller_git_top_level()
        if controller_top_level is None:
            return True

        top_level = self._git_top_level(swarm_path)
        if top_level != swarm_path or top_level == controller_top_level:
            return False
        return swarm_path in self._registered_worktree_paths()

    def acquire(self, timeout_sec: float = 60.0) -> Optional[Path]:
        """
        租用一個閒置的 Swarm 目錄。支援跨進程的原子鎖定。
        """
        if not self.swarm_dirs:
            return None

        eligible_dirs = [
            swarm_dir for swarm_dir in self.swarm_dirs
            if self.is_independently_registered_worktree(swarm_dir)
        ]
        if not eligible_dirs:
            logger.warning("⚠️ [SwarmBroker] No independently registered swarm worktrees available.")
            return None

        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            for swarm_dir in eligible_dirs:
                lock_file = swarm_dir / ".swarm_lock"
                try:
                    # Attempt to create the lock file exclusively for cross-process safety
                    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    
                    # 🚀 [Shared Cache] 加速啟動：掛載重型依賴
                    self._mount_shared_cache(swarm_dir)
                    
                    logger.debug(f"🐝 [SwarmBroker] Acquired swarm sandbox: {swarm_dir.name}")
                    return swarm_dir
                except FileExistsError:
                    continue  # Already locked by another process/thread
            time.sleep(0.5)
        
        logger.error("❌ [SwarmBroker] Timeout waiting for an available Swarm directory.")
        return None

    def _mount_shared_cache(self, swarm_dir: Path):
        """
        使用軟連結掛載 .venv 與 node_modules，避免磁碟 I/O 瓶頸。
        """
        for cache_dir in [".venv", "node_modules", ".ruff_cache"]:
            src = self.workspace / cache_dir
            dst = swarm_dir / cache_dir
            if src.exists() and not dst.exists():
                try:
                    os.symlink(src, dst)
                except Exception as e:
                    logger.warning(f"⚠️ [SwarmBroker] Link failed for {cache_dir}: {e}")

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
            raw_path = Path(rel_path)
            src = raw_path if raw_path.is_absolute() else self.workspace / raw_path
            try:
                dst_rel = src.resolve().relative_to(self.workspace)
            except ValueError:
                dst_rel = raw_path if not raw_path.is_absolute() else Path(raw_path.name)
            dst = swarm_dir / dst_rel
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.resolve() == dst.resolve():
                    continue
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

    def release(self, swarm_dir: Path):
        """
        清空 Swarm 目錄內容（還原為初始狀態）並解除鎖定。
        實施重用 (Reuse) 策略：保留 .git 並使用 git reset/clean。
        """
        if not swarm_dir or not swarm_dir.exists():
            return
            
        lock_file = swarm_dir / ".swarm_lock"
        if not self.is_independently_registered_worktree(swarm_dir):
            if lock_file.exists():
                lock_file.unlink()
            logger.warning("⚠️ [SwarmBroker] Refused to clean unregistered swarm placeholder: %s", swarm_dir)
            return

        try:
            for cache_dir in [".venv", "node_modules", ".ruff_cache"]:
                mounted = swarm_dir / cache_dir
                if mounted.is_symlink():
                    mounted.unlink()
            # 實施重用策略 (Reuse)
            is_git = (swarm_dir / ".git").exists()
            if is_git:
                logger.debug(f"🐝 [SwarmBroker] Reusing git worktree in {swarm_dir.name}")
                import subprocess
                # 快速重設 git 狀態
                subprocess.run(["git", "checkout", "."], cwd=swarm_dir, capture_output=True)
                subprocess.run(["git", "clean", "-fd"], cwd=swarm_dir, capture_output=True)
            else:
                # Fallback: Clean up all contents EXCEPT the lock file
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
            logger.debug(f"🐝 [SwarmBroker] Released and reset swarm sandbox: {swarm_dir.name}")
        except Exception as e:
            logger.error(f"❌ [SwarmBroker] Error releasing swarm {swarm_dir.name}: {e}")
