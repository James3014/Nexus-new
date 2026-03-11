#!/usr/bin/env -S uv run --script
# 🛡️ Codex-Verified: c016a21 (2026-03-06)
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import os
import json
import glob
import subprocess
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


def resolve_vault_root() -> Path:
    env_root = os.getenv("VAULT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p
    script_path = Path(__file__).resolve()
    for parent in [script_path.parent, *script_path.parents]:
        if (parent / "00_System_Knowledge").exists() and (parent / "01_Operations").exists():
            return parent
    return script_path.parents[1]


TRANSCRIPTS_DIR = Path.home() / ".muse_transcripts"
SUBCONSCIOUS_FILE = resolve_vault_root() / "00_System_Knowledge" / "01_Operations" / "04_Subconscious_Memory.md"


def list_transcript_files() -> List[str]:
    if not TRANSCRIPTS_DIR.exists():
        return []
    return sorted(glob.glob(str(TRANSCRIPTS_DIR / "*.jsonl")))


def load_history(files: List[str]) -> List[Dict[str, Any]]:
    history = []
    for f_path in files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        history.append({
                            "timestamp": data.get("timestamp"),
                            "status": data.get("status"),
                            "diff": data.get("diff"),
                            "report": data.get("report")
                        })
                    except Exception as parse_e:
                        print(f"⚠️ 解析行內容失敗，跳過該行: {parse_e}")
        except Exception as e:
            print(f"⚠️ 讀寫 {f_path} 失敗: {e}")
            
    history.sort(key=lambda x: str(x.get("timestamp", "")))
    return history


def build_prompt(history: List[Dict[str, Any]]) -> str:
    prompt = """你是 Muse-Core 開發生態系中的「潛意識大腦 (Subconscious)」。
以下是一位 AI Agent 在修改程式碼時，與 Codex-Loop 審查系統的來回拉扯紀錄（Transcript）。
紀錄中包含了它被退回（FAIL）時的 Codex 錯誤報告，以及它最終成功過關（PASS）時的 Git Diff。

請你化身為一位資深的 Technical Lead，反思這段開發歷程。
你的任務是「淬鍊出黃金教訓」，告訴未來的自己與其他 Agent，在遇到類似需求時，應該**避免什麼錯**，並**採取什麼寫法**。

【輸出格式限制】
1. 只輸出 Markdown 的項目符號清單（- ），不要有任何前言或結語（例如：「好的，以下是...」）。
2. 每條教訓必須具體且具可操作性，不可說廢話。例如：「當處理 FastAPI CORS 時，必須在路由之前掛載 Middleware，否則即使設定了還是會被擋」。
3. 語氣請客觀、精煉，直接陳述技術規則。每次產出最多 3 條最核心的血淚教訓，不痛不癢的不要寫。

【開發紀錄】
"""
    for entry in history:
        status = entry.get("status")
        report = entry.get("report", "")
        diff = entry.get("diff", "")
        prompt += f"\n=== 事件狀態: {status} ===\n"
        if status == "FAIL" and report:
            prompt += f"[Codex 審查錯誤報告]:\n{report[:1500]}...\n\n"
        elif status == "PASS" and diff:
            prompt += f"[最終過關的 Git Diff]:\n{diff[:2000]}...\n\n"
    return prompt


def run_reflection(prompt: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(prompt)
            tmp_path = tmp.name

        # 使用 shutil 動態尋找 codex 執行檔路徑以維持移植性
        codex_bin = shutil.which("codex") or "codex"
        
        # 使用 -ic 確保載入 .zshrc 中的環境變數與 PATH，以應對非交互式環境中的執行失敗
        result = subprocess.run(
            ["zsh", "-ic", f"'{codex_bin}' exec - < '{tmp_path}'"],
            capture_output=True,
            text=True
        )
        os.remove(tmp_path)
        
        reflection = result.stdout.strip()
        if result.returncode != 0 or not reflection:
            print(f"❌ 呼叫 LLM 失敗：{result.stderr}")
            return None
        return reflection
    except Exception as e:
        print(f"❌ 執行 Subprocess 發生錯誤: {e}")
        return None


def write_subconscious(reflection: str) -> bool:
    if not SUBCONSCIOUS_FILE.exists():
        print("⚠️ 找不到 04_Subconscious_Memory.md 大腦檔案。")
        return False
        
    try:
        content = SUBCONSCIOUS_FILE.read_text(encoding="utf-8")
        target_header = "## 🐛 過往除錯血淚史 (Debugging Lessons)"
        if target_header not in content:
            print("⚠️ 找不到過往除錯血淚史的標題，請確認 04_Subconscious_Memory.md 的結構。")
            return False
            
        new_date = datetime.now().strftime("%Y-%m-%d")
        inserted = f"\n### {new_date} 反思\n{reflection}\n"
        parts = content.split(target_header)
        body = parts[1].replace("- 尚未收集到任何記憶。\n", "", 1)
        new_content = parts[0] + target_header + inserted + body
        SUBCONSCIOUS_FILE.write_text(new_content, encoding="utf-8")
        print("✅ 成功將記憶寫入潛意識庫。")
        return True
    except Exception as e:
        print(f"❌ 寫入潛意識發生錯誤: {e}")
        return False


def cleanup(files: List[str]) -> None:
    for f_path in files:
        try:
            os.remove(f_path)
        except Exception as e:
            print(f"⚠️ 清理 {f_path} 失敗: {e}")
    print("♻️ 已清理消化完成的記憶碎片。")


def process_transcripts() -> None:
    files = list_transcript_files()
    if not files:
        print("沒有待處理的潛意識記憶碎片。")
        return

    print(f"🧠 偵測到 {len(files)} 份潛意識記憶碎片，開始反思淬鍊...")

    history = load_history(files)
    if not history:
        print("⚠️ 沒有可用的歷程資料，保留原始碎片供後續人工檢查。")
        return

    prompt = build_prompt(history)
    reflection = run_reflection(prompt)
    if not reflection:
        print("⚠️ 反思產生失敗，保留原始碎片以避免資料遺失。")
        return

    print("💡 提煉教訓：")
    print(reflection)

    if write_subconscious(reflection):
        cleanup(files)
    else:
        print("⚠️ 寫入失敗，保留原始碎片以避免資料遺失。")


if __name__ == "__main__":
    process_transcripts()
