#!/usr/bin/env python3
"""
🛡️ Nexus Rollback Guard — GIT-powered Resilience (v23.8 FIXED)

Provides Git-based snapshotting and environment reset capabilities.

CRITICAL FIX (v23.8.1): Uses `git checkout .` instead of `git clean -fd`
to avoid destroying untracked/new files created during the repair session.
Only tracked file modifications are reverted.
"""
import subprocess
import os
import sys
from pathlib import Path


class RollbackGuard:
    """🛡️ Nexus Rollback Guard — GIT-powered Resilience"""

    def __init__(self, repo_root=None):
        self.repo_root = Path(repo_root or os.getcwd()).resolve()
        self.initial_hash = None
        self.stash_id = None

    def capture_state(self):
        """Capture current HEAD commit hash."""
        try:
            self.initial_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo_root),
                text=True,
            ).strip()
            print(f"📦 [Rollback] State captured. HEAD: {self.initial_hash[:8]}")
        except Exception as e:
            print(f"⚠️ [Rollback] State capture failed: {e}")

    def reset_to_head(self):
        """
        Reset TRACKED files to HEAD state.

        IMPORTANT: Uses `git checkout .` (NOT `git clean -fd`).
        This only reverts modifications to tracked files.
        Untracked/new files are preserved — this is intentional,
        as the repair loop may have created new files that should not be destroyed.
        """
        print("🚨 [Rollback] Reverting tracked file modifications to HEAD...")
        try:
            subprocess.run(
                ["git", "checkout", "."],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
            )
            print("✅ [Rollback] Tracked files restored to clean state.")
            print("   ℹ️  Untracked/new files are preserved (by design).")
        except Exception as e:
            print(f"❌ [Rollback] Reset FAILED: {e}")

    def hard_reset(self):
        """
        Nuclear option: revert ALL changes including untracked files.
        Only used when explicitly requested by the human operator.
        """
        print("☢️ [Rollback] HARD RESET — destroying ALL uncommitted changes...")
        try:
            subprocess.run(
                ["git", "reset", "--hard", self.initial_hash or "HEAD"],
                cwd=str(self.repo_root),
                check=True,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=str(self.repo_root),
                check=True,
            )
            print("✅ [Rollback] Environment fully reset (tracked + untracked).")
        except Exception as e:
            print(f"❌ [Rollback] Hard reset FAILED: {e}")


if __name__ == "__main__":
    guard = RollbackGuard()
    guard.capture_state()
    print("Test: rollback_guard imported and initialized successfully.")
