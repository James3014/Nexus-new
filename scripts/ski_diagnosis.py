#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import json
import subprocess
import re
import argparse

SEARCH_BIN = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/scripts/brain_search_v2.py"
OPENCLAW_BIN = "/Users/jameschen/.npm-global/bin/openclaw"


def diagnose(symptom):
    print(f"🏂 [滑雪診斷引擎] 正在分析症狀：{symptom}")

    # 1. 檢索滑雪教案
    print("🔍 正在從大腦檢索相關教案...")
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
            symptom,
            "--limit",
            "3",
            "--json",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        results = json.loads(res.stdout)
    except Exception as e:
        print(f"❌ 檢索失敗: {e}")
        return

    if not results:
        print("⚠️ 找不到相關的滑雪教案。")
        return

    # 2. 組合背景知識 (Context)
    context_text = ""
    sources = []
    for res in results:
        meta = json.loads(res.get("metadata", "{}"))
        source = meta.get("source", "Unknown")
        # 簡單過濾，只取跟滑雪/教學有關的內容
        if (
            "滑雪" in source
            or "教案" in source
            or "Skiing" in source
            or "教學" in source
        ):
            text = res.get("text", "")
            context_text += f"來源: {source}\n內容摘要: {text}\n\n"
            sources.append(source)

    if not context_text:
        # 如果沒有命中含有特定目錄特徵的，就直接用全部
        for res in results:
            meta = json.loads(res.get("metadata", "{}"))
            source = meta.get("source", "Unknown")
            text = res.get("text", "")
            context_text += f"來源: {source}\n內容摘要: {text}\n\n"
            sources.append(source)

    print("🧠 正在生成專業處方箋...")
    # 3. 呼叫 OpenClaw LLM 進行診斷生成
    prompt = f"""
你是一位頂級滑雪教練 (Ski Instructor)。請根據以下我知識庫中的教案內容，診斷學生的問題，並給出具體的修復計畫。

學生症狀：{symptom}

知識庫教案參考：
{context_text}

請嚴格依照以下格式輸出（繁體中文，語氣專業且具鼓勵性）：
### 🏂 診斷結果：
(簡述問題成因)

### 🛠️ 修復計畫 (處方箋)：
1. (步驟1)
2. (步驟2)
...
"""
    try:
        cmd = [OPENCLAW_BIN, "agent", "--agent", "main", "--message", prompt, "--json"]
        # 由於 openclaw 會輸出 JSON 包裝的結果，我們需要擷取其中的 payload
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # OpenClaw 輸出可能包含一些非 JSON 前綴，用正則擷取 JSON 區塊
        match = re.search(r"\{.*\}", process.stdout, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            # 兼容不同版本的 OpenClaw 輸出結構
            payloads = data.get("result", {}).get("payloads") or data.get(
                "payloads", []
            )
            output_text = payloads[0].get("text", "無內容") if payloads else "無內容"

            print("\n" + "=" * 50)
            print(output_text)
            print("=" * 50)
            print("\n📚 [參考文獻]:")
            for s in set(sources):
                print(f"- {s}")
        else:
            # 如果解析不到 JSON，直接印出 stdout 看看
            print("⚠️ 無法解析 LLM 結構化輸出，原始回應如下：")
            print(process.stdout)

    except Exception as e:
        print(f"❌ 診斷生成失敗: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SKIDIY 動態診斷引擎")
    parser.add_argument("symptom", help="請描述學生的滑雪症狀 (例如：換刃時提早轉肩)")
    args = parser.parse_args()

    diagnose(args.symptom)
