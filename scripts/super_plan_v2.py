#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import os
import time
import re
import argparse

PLAN_DIR = "/Users/jameschen/Downloads/obsidian/知識庫/01_Projects/SKIDIY/Plans"


def create_plan(topic, description):
    if not os.path.exists(PLAN_DIR):
        os.makedirs(PLAN_DIR, exist_ok=True)

    date_str = time.strftime("%Y-%m-%d")
    filename = f"{date_str}-{topic.replace(' ', '_')}.md"
    filepath = os.path.join(PLAN_DIR, filename)

    content = f"""---
title: Superpowers 微計畫：{topic}
date: {date_str}
last_updated: {time.strftime("%Y-%m-%d %H:%M:%S")}
status: in_progress
type: micro-plan
---

# 📝 微計畫：{topic}

> **任務描述**：{description}

---

## 🧠 1. 設計與上下文 (Design & Context)
- [ ] 確定受影響的檔案路徑。
- [ ] 蘇格拉底提問：這項變更是否有更簡單的實作方式？

## 📝 2. 原子化執行步驟 (Atomic Steps)
*每個步驟預計 2-5 分鐘完成*

1. **[RED]** 撰寫失敗測試檔。
2. **[GREEN]** 實作最少代碼使測試通過。
3. **[REFACTOR]** 優化代碼結構而不改變行為。
4. [ ] 步驟 1：
5. [ ] 步驟 2：

## 🧪 3. 驗證方式 (Verification)
- [ ] 執行指令：`pytest` 或 `python3 -m unittest`
- [ ] 預期結果：所有測項通過。
- [ ] 執行指令：`codex-guard` 進行跨模型審查。
- [ ] 預期結果：Codex 回傳 VERDICT: PASS。

---
%% 
由 Muse-Core Superpowers v2 自動生成。
工程紀律：計畫與執行同步，自動化追蹤。
%%
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def update_plan(filepath, check_text=None, status=None):
    if not os.path.exists(filepath):
        print(f"❌ 找不到計畫檔案：{filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 更新狀態
    if status:
        content = re.sub(r"status: .*", f"status: {status}", content)

    # 更新最後更新時間
    content = re.sub(
        r"last_updated: .*",
        f"last_updated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        content,
    )

    # 勾選步驟
    if check_text:
        # 嘗試精確匹配或語義匹配 [ ] 步驟內容
        # 這裡使用簡單的正則替換
        pattern = rf"- \[ \] (.*{re.escape(check_text)}.*)"
        if re.search(pattern, content):
            content = re.sub(pattern, r"- [x] \1", content)
            print(f"✅ 已勾選步驟：{check_text}")
        else:
            # 嘗試匹配帶數字的步驟，例如 "1. **[RED]**"
            pattern_numeric = rf"(\d+\. .*?{re.escape(check_text)}.*)"
            # 對於數字步驟，我們在前面加個 [x] 或者改變顏色？
            # 這裡統一改為 Markdown 任務格式或在行尾加勾
            if re.search(pattern_numeric, content):
                content = re.sub(pattern_numeric, r"✅ \1", content)
                print(f"✅ 已標記完成：{check_text}")
            else:
                print(f"⚠️ 找不到匹配的步驟：{check_text}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def main():
    parser = argparse.ArgumentParser(description="Superpowers 微計畫管理器 v2")
    subparsers = parser.add_subparsers(dest="command")

    # Create command
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("topic", help="計畫主題")
    create_parser.add_argument("description", help="計畫描述")

    # Update command
    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("file", help="計畫檔案路徑")
    update_parser.add_argument("--check", help="要勾選的步驟文字")
    update_parser.add_argument("--status", help="更新 YAML 狀態")

    args = parser.parse_args()

    if args.command == "create":
        path = create_plan(args.topic, args.description)
        print(f"✅ 微計畫已產出：{path}")
    elif args.command == "update":
        if update_plan(args.file, args.check, args.status):
            print(f"✅ 計畫已更新：{args.file}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
