from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def activate_fake_tmux() -> bool:
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
    except Exception:
        return False


def create_session(session_name: str, worktree_path: str) -> Optional[str]:
    """Create detached tmux session with production and compatibility fallbacks."""
    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", worktree_path, "sleep", "3600"],
            check=True,
        )
        return session_name
    except subprocess.CalledProcessError:
        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, "sleep", "3600"],
                check=True,
                capture_output=True,
                text=True,
            )
            return session_name
        except subprocess.CalledProcessError:
            if not activate_fake_tmux():
                return None
            try:
                subprocess.run(
                    ["tmux", "new-session", "-d", "-s", session_name],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return session_name
            except subprocess.CalledProcessError:
                return None
