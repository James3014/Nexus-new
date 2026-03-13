#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import sys
import os
from datetime import datetime

KB_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"

def get_registry_path(filename):
    local_path = os.path.join(os.getcwd(), "01_Operations", filename)
    if os.path.exists(local_path): return local_path
    return os.path.join(KB_DIR, "01_Operations", filename)

HABIT_REGISTRY = get_registry_path("02_Habit_Registry.md")

def refine():
    print("🧬 啟動 Muse-Core 自進化重構引擎 (Self-Refiner)...")
    with open(HABIT_REGISTRY, "r", encoding="utf-8") as f: content = f.read()
    if "## 🧬 系統自進化與防禦更新" in content:
        print("ℹ️  註冊表已有進化規則，跳過重複寫入。")
        return
    new_rules = """
## 🧬 系統自進化與防禦更新 (Auto-Refined)
- **[環境防禦]**: 凡執行需要特定套件之 Python 腳本，**強制使用 uv run --with <package>**。
- **[字串防禦]**: 撰寫 Python f-string 時，若跨行則強制使用三引號。
- **[多開防禦]**: 嚴禁在髒主幹中切換分支。
"""
    with open(HABIT_REGISTRY, "a", encoding="utf-8") as f: f.write("\n" + new_rules)
    print(f"✅ 系統自進化完成！已更新: {HABIT_REGISTRY}")

if __name__ == "__main__": refine()
