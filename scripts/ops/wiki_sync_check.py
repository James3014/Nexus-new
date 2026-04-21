#!/usr/bin/env python3
import argparse
import subprocess
import sys

def get_changed_files(mode="worktree"):
    """獲取變更檔案列表"""
    try:
        if mode == "staged":
            cmd = ["git", "diff", "--cached", "--name-only"]
        else:
            # worktree: includes staged + unstaged (excluding untracked)
            # Use diff HEAD to get all tracked changes
            cmd = ["git", "diff", "HEAD", "--name-only"]
            
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        files = res.stdout.strip().split("\n")
        return [f for f in files if f]
    except subprocess.CalledProcessError:
        return []

def check_sync(mode="worktree"):
    changed_files = get_changed_files(mode)
    
    code_patterns = [
        "scripts/ops/",
        "scripts/engine/",
        "nexus/core/"
    ]
    
    wiki_patterns = [
        "nexus_wiki_vault/"
    ]
    
    changelog_path = "nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md"
    
    code_changed = False
    wiki_changed = False
    
    for f in changed_files:
        # Check if it's code change
        if any(f.startswith(p) and f.endswith(".py") for p in code_patterns):
            code_changed = True
        
        # Check if it's wiki change
        if any(f.startswith(p) and f.endswith(".md") for p in wiki_patterns):
            wiki_changed = True
        if f == changelog_path:
            wiki_changed = True

    if code_changed and not wiki_changed:
        print("❌ [WIKI-SYNC-BLOCK] Code changes detected in protected paths, but no Wiki updates found in nexus_wiki_vault/.")
        print(f"💡 Suggestion: Update nexus_wiki_vault/ or {changelog_path}")
        return 2
    
    if code_changed:
        print("✅ [WIKI-SYNC] Code and Wiki changes are synchronized.")
    else:
        print("✅ [WIKI-SYNC] No protected code changes detected.")

    return 0

def main():
    parser = argparse.ArgumentParser(description="Wiki Sync Check")
    parser.add_argument("--mode", choices=["staged", "worktree"], default="worktree")
    args = parser.parse_args()
    
    sys.exit(check_sync(args.mode))

if __name__ == "__main__":
    main()
