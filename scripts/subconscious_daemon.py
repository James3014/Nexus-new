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
    # 1) Explicit env override
    for key in ("VAULT_ROOT", "MUSE_VAULT_ROOT"):
        env_root = os.getenv(key)
        if env_root:
            p = Path(env_root).expanduser().resolve()
            if p.exists():
                # Allow either vault root (.../知識庫) or parent (.../obsidian)
                if (p / "00_System_Knowledge").exists():
                    return p
                if (p / "知識庫" / "00_System_Knowledge").exists():
                    return (p / "知識庫").resolve()

    # 2) Common local defaults
    defaults = [
        Path("/Users/jameschen/Downloads/obsidian/知識庫"),
        Path("/Users/jameschen/Downloads/obsidian"),
    ]
    for p in defaults:
        if p.exists():
            if (p / "00_System_Knowledge").exists():
                return p.resolve()
            if (p / "知識庫" / "00_System_Knowledge").exists():
                return (p / "知識庫").resolve()

    # 3) Repo-relative discovery
    script_path = Path(__file__).resolve()
    for parent in [script_path.parent, *script_path.parents]:
        if (parent / "00_System_Knowledge").exists() and (parent / "01_Operations").exists():
            return parent
    return script_path.parents[1]


def resolve_subconscious_file(vault_root: Path) -> Path:
    candidates = [
        vault_root / "00_System_Knowledge" / "01_Operations" / "04_Subconscious_Memory.md",
        vault_root / "01_Operations" / "04_Subconscious_Memory.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Default write target (if file does not exist yet)
    return candidates[0]


TRANSCRIPTS_DIR = Path.home() / ".muse_transcripts"
SUBCONSCIOUS_FILE = resolve_subconscious_file(resolve_vault_root())


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


def fallback_reflection(history: List[Dict[str, Any]]) -> str:
    """Offline-safe fallback when codex is unavailable."""
    fail_reports = "\n".join(
        [str(h.get("report", "")) for h in history if h.get("status") == "FAIL"]
    ).lower()
    tips = []
    if "network" in fail_reports or "websocket" in fail_reports or "lookup address" in fail_reports:
        tips.append("- 網路依賴工具需設置 fail-open/fallback；不可把外部連線失敗當成邏輯失敗。")
    if "json" in fail_reports or "schema" in fail_reports or "parse" in fail_reports:
        tips.append("- LLM 輸出需做容錯解析與欄位驗證，避免硬性精確比對造成誤判。")
    if "lock" in fail_reports or "/tmp/" in fail_reports:
        tips.append("- 鎖檔與狀態檔必須按專案隔離，避免跨 repo 互相阻塞。")
    if not tips:
        tips.append("- 提交前先做最小可驗證檢查（語法、路徑、關鍵流程），再進入審查迴圈。")
        tips.append("- 對外部服務的失敗要分類（網路/權限/邏輯），並提供可重試策略。")
    return "\n".join(tips[:3])


def run_reflection(prompt: str, history: List[Dict[str, Any]]) -> Optional[str]:
    try:
        # 使用 shutil 動態尋找 codex 執行檔路徑以維持移植性
        codex_bin = shutil.which("codex") or "codex"
        result = subprocess.run(
            [codex_bin, "exec", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        raw = result.stdout.strip()
        # 僅保留符合規範的條列教訓，避免把工具雜訊寫入記憶檔
        bullet_lines = [ln.strip() for ln in raw.splitlines() if ln.strip().startswith("- ")]
        reflection = "\n".join(bullet_lines[:3]).strip()
        if result.returncode != 0 or not reflection:
            print("⚠️ codex 反思不可用，改用離線 fallback 規則產出教訓。")
            return fallback_reflection(history)
        return reflection
    except Exception as e:
        print(f"⚠️ 反思子程序異常，改用離線 fallback：{e}")
        return fallback_reflection(history)


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
    reflection = run_reflection(prompt, history)
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
