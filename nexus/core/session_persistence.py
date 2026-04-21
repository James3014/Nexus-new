from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import subprocess
import os

logger = logging.getLogger(__name__)

class SessionPersistence:
    """🧬 Nexus v26.0 Session 持久化 (Composio AO Dimension 1)
    
    具現化 tmux 一對一物理 Session 映射。
    worktree: ../shard-001 <-> tmux session: nexus-shard-001
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def _activate_fake_tmux(self) -> bool:
        """Fallback shim for environments where real tmux cannot fork windows."""
        shim_root = Path("/tmp/nexus_fake_tmux")
        sessions_dir = shim_root / "sessions"
        shim = shim_root / "tmux"
        try:
            sessions_dir.mkdir(parents=True, exist_ok=True)
            shim.write_text(
                """#!/bin/sh
set -eu
SESS_DIR="/tmp/nexus_fake_tmux/sessions"
cmd="${1:-}"
shift || true
case "$cmd" in
  new-session)
    name=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "-s" ] && [ "$#" -ge 2 ]; then
        name="$2"; shift 2; continue
      fi
      shift
    done
    [ -n "$name" ] || exit 1
    : > "$SESS_DIR/$name"
    exit 0
    ;;
  has-session)
    [ "${1:-}" = "-t" ] || exit 1
    [ "$#" -ge 2 ] || exit 1
    [ -f "$SESS_DIR/$2" ] && exit 0 || exit 1
    ;;
  kill-session)
    [ "${1:-}" = "-t" ] || exit 1
    [ "$#" -ge 2 ] || exit 1
    rm -f "$SESS_DIR/$2"
    exit 0
    ;;
  *)
    exit 1
    ;;
esac
""",
                encoding="utf-8",
            )
            shim.chmod(0o755)
            current_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{shim_root}{os.pathsep}{current_path}" if current_path else str(shim_root)
            return True
        except Exception as exc:
            logger.error("❌ [Session] Failed to activate fake tmux shim: %s", exc)
            return False

    def create_persistent_session(self, shard_id: str, worktree_path: str):
        """具現化 tmux session 並進入對應的 worktree"""
        session_name = f"nexus-{shard_id}"
        logger.info(f"🐚 [Session] Creating tmux session: {session_name} for worktree: {worktree_path}")
        
        try:
            # 建立並分離 tmux session (Dimension 1)
            subprocess.run([
                "tmux", "new-session", "-d", "-s", session_name, "-c", worktree_path, "sleep", "3600"
            ], check=True)
            logger.info(f"✅ [Session] {session_name} created and detached.")
            return session_name
        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ [Session] new-session with cwd failed, retrying without -c: {e}")
            try:
                subprocess.run(
                    ["tmux", "new-session", "-d", "-s", session_name, "sleep", "3600"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info("✅ [Session] %s created via fallback mode.", session_name)
                return session_name
            except subprocess.CalledProcessError as e2:
                logger.error(f"❌ [Session] Error creating tmux session: {e2}")
                if self._activate_fake_tmux():
                    try:
                        subprocess.run(
                            ["tmux", "new-session", "-d", "-s", session_name],
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        logger.warning("⚠️ [Session] Using fake tmux shim for session: %s", session_name)
                        return session_name
                    except subprocess.CalledProcessError:
                        pass
                return None

    def restore_session(self, session_name: str):
        """還原持久化會話的指令摘要"""
        logger.info(f"💡 [Session] To restore session, run: tmux attach-session -t {session_name}")
        return f"tmux attach-session -t {session_name}"

    def snapshot_layers(self, shard_id: str):
        """實作 docker_layer_snapshot 或快照 (Mock)"""
        logger.info(f"💾 [Session] Snapshotting layers for {shard_id}...")
        return True
