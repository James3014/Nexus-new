#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import json
import os
import subprocess
import re
import time

EVENT_STORE = (
    "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/EVENT_STORE.jsonl"
)
OPENCLAW_BIN = "/Users/jameschen/.npm-global/bin/openclaw"


def reconstruct_state():
    if not os.path.exists(EVENT_STORE) or os.path.getsize(EVENT_STORE) == 0:
        print("ℹ️ 事件倉庫為空，跳過重建。")
        return

    print("🔍 正在從事件倉庫讀取最新紀錄...")
    with open(EVENT_STORE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        if not lines:
            return
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except:
                continue
        if not events:
            return
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except:
                continue

    recent_events = events[-8:]
    events_summary = ""
    for e in recent_events:
        events_summary += f"[{e.get('timestamp')}] {e.get('description')}\n"

    prompt = f"請將以下事件流摘要為 Markdown 格式的 CURRENT_STATE.md。僅輸出 Markdown 正文，禁止日誌。\n\n事件流：\n{events_summary}"

    try:
        print("🧠 呼叫 OpenClaw 進行語義狀態投影...")
        cmd = [
            OPENCLAW_BIN,
            "agent",
            "--agent",
            "main",
            "--session-id",
            "state_sync_" + str(int(time.time())),
            "--message",
            prompt,
            "--json",
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        match = re.search(r"\{.*\}", process.stdout, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            payloads = data.get("result", {}).get("payloads") or data.get(
                "payloads", []
            )
            output_text = payloads[0].get("text", "") if payloads else ""

            if (
                not output_text
                or len(output_text) < 50
                or "Context overflow" in output_text
                or "Error" in output_text
            ):
                print("⚠️  偵測到疑似錯誤的回應內容，取消寫入。")
                return
        else:
            return

        target_path = (
            "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/CURRENT_STATE.md"
        )
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("# 📡 Muse-Core 當前狀態 (由事件溯源自動生成)\n\n")
            f.write(
                f"> **生成時間**: {subprocess.check_output(['date']).decode().strip()}\n\n"
            )
            f.write(output_text.strip())

        print(f"✨ 狀態已安全更新：{target_path}")
    except Exception as e:
        print(f"❌ 狀態重建崩潰: {e}")


if __name__ == "__main__":
    reconstruct_state()
