import os
import subprocess
import sys

def review_and_merge():
    """🛡️ Nexus L2 Human-Gate: Proposal Review (Automation Phase 2)"""
    print("🌙 [NightShift Update] New Repair Proposal Detected.")
    
    # 1. 顯示 Diff
    print("-" * 40)
    print("🚀 Proposed Code Changes (v9.2):")
    subprocess.run(["git", "diff", "--staged"], check=False)
    print("-" * 40)
    
    # 2. 交互式審核
    try:
        choice = input("👉 是否批准合併到主分支？ (y/n/skip): ").strip().lower()
    except EOFError:
        print("⚠️ No input detected, skipping.")
        return

    if choice == 'y':
        print("✅ [APPROVED] Committing changes...")
        subprocess.run(["git", "commit", "-m", "fix(nexus): auto-repair proposal applied (L2)"], check=False)
        print("🎉 Successfully merged.")
    elif choice == 'n':
        print("❌ [REJECTED] Rolling back and logging trauma...")
        subprocess.run(["git", "reset", "--hard"], check=False)
        # 觸發 TraumaEngine 紀錄
        # uv run scripts/ops/log_trauma.py "Human rejection of proposal"
    else:
        print("⌛ [SKIPPED] Review deferred.")

if __name__ == "__main__":
    review_and_merge()
