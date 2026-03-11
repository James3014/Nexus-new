#!/usr/bin/env python3
# 🛡️ Codex-Verified: Lvl13-Verified (2026-03-03)
import sys

REGISTRY_PATH = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/03_Automation_Functional_Registry.md"


def run_check(new_tool_intent):
    print(f"🕵️ 正在檢索現有工具鏈以對位意圖：{new_tool_intent}")
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = f.read()
    except FileNotFoundError:
        print(f"❌ 找不到註冊表：{REGISTRY_PATH}")
        return

    print("--- [現有功能概覽] ---")
    lines = registry.split("\n")
    for line in lines:
        if line.startswith("## "):
            print(f"Existing Tool: {line.strip()}")

    print("\n--- [自我反省] ---")
    print(f"1. {new_tool_intent} 是否已被上述工具覆蓋？")
    print("2. git-manager 或 Superpowers 技能是否已具備此功能？")
    print("------------------")
    print("⚠️  若無充分證據證明其獨特性，禁止建立新腳本。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 redundancy_check.py <新工具意圖>")
    else:
        run_check(sys.argv[1])
