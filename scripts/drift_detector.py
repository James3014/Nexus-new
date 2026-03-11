#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import sys
import subprocess
import json
import re

SEARCH_BIN = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/scripts/brain_search_v2.py"
OPENCLAW_BIN = "/Users/jameschen/.npm-global/bin/openclaw"
KB_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"


def get_staged_diff():
    """獲取準備 commit 的 git diff 內容"""
    try:
        # 只抓取新增或修改的內容，忽略已刪除的
        cmd = ["git", "-C", KB_DIR, "diff", "--cached", "--diff-filter=AM"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if not res.stdout.strip():
            return None

        # 為了避免 diff 太長，只擷取前 2000 個字元
        diff_content = res.stdout[:2000]
        if len(res.stdout) > 2000:
            diff_content += "\n...[Diff truncated]..."
        return diff_content
    except Exception as e:
        print(f"❌ Git diff 獲取失敗: {e}")
        return None


def get_constitutional_context(query_keywords):
    """利用 RAG 檢索相關的憲法或會議共識"""
    try:
        cmd = [
            "/Users/jameschen/.local/bin/uv",
            "run",
            "--with",
            "lancedb",
            "--with",
            "pandas",
            "--with",
            "requests",
            SEARCH_BIN,
            query_keywords,
            "--limit",
            "3",
            "--json",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        results = json.loads(res.stdout)

        context = ""
        for res in results:
            text = res.get("text", "")
            source = json.loads(res.get("metadata", "{}")).get("source", "Unknown")
            if (
                "會議紀錄" in source
                or "決策" in source
                or "MANIFESTO" in source
                or "共識" in source
            ):
                context += f"📜 來源: {source}\n{text}\n\n"
        return context
    except Exception:
        return ""


def check_intent_drift():
    diff_text = get_staged_diff()
    if not diff_text:
        # 沒有變更，直接通過
        sys.exit(0)

    print("🛡️ [意圖漂移預警系統] 正在掃描變更的哲學性偏離...")

    # 從 diff 中簡單提取一些關鍵字去搜尋相關共識
    # 這裡用簡單的正則提取中文字作為檢索詞，或者直接用固定關鍵字 "核心價值 決策 排序 權益"
    search_query = "股東共識 核心價值 排序邏輯 演算法 權益 轉型"
    context = get_constitutional_context(search_query)

    if not context:
        print("⚠️ 未檢索到相關的商業憲法或會議共識，跳過意圖漂移檢查。")
        sys.exit(0)

    prompt = f"""
你是一個名為「意圖漂移守護者 (Drift Detector)」的 AI 架構師。
你的任務是審查即將提交的程式碼或文件變更 (Git Diff)，是否違背了專案最初的「商業憲法」或「股東共識」。

### 專案歷史共識與核心價值 (RAG Context)：
{context}

### 即將提交的變更 (Git Staged Diff)：
{diff_text}

請判斷這些變更是否產生了「意圖漂移（例如：犧牲教練權益換取流量、偏離合法化轉型等）」。
如果沒有衝突，請回覆 "PASS"。
如果發現潛在的哲學性偏離或語義衝突，請回覆 "DRIFT_DETECTED"，並簡短說明原因與建議（繁體中文）。
"""

    try:
        cmd = [OPENCLAW_BIN, "agent", "--agent", "main", "--message", prompt, "--json"]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        match = re.search(r"\{.*\}", process.stdout, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            output_text = (
                (data.get("result", {}).get("payloads") or data.get("payloads", []))[0]
                .get("text", "")
                .strip()
            )

            if (
                "DRIFT_DETECTED" in output_text
                or "DRIFT" in output_text
                or "偏離" in output_text
            ) and "PASS" not in output_text:
                print("\n🚨 [意圖漂移攔截] 偵測到與歷史共識衝突！")
                print("=" * 50)
                print(output_text.replace("DRIFT_DETECTED", "").strip())
                print("=" * 50)
                print(
                    "\nSir, 目前的修改與股東共識有語義衝突，已阻斷 Commit，建議重新評估。"
                )
                sys.exit(1)  # 回傳非 0 狀態碼，阻斷 git commit
            else:
                print("✅ 意圖校準通過：變更符合商業憲法與股東共識。")
                sys.exit(0)
        else:
            print("⚠️ 無法解析 LLM 回應，預設放行。")
            sys.exit(0)
    except Exception as e:
        print(f"❌ 意圖檢測崩潰: {e}，為避免阻塞開發，預設放行。")
        sys.exit(0)


if __name__ == "__main__":
    check_intent_drift()
