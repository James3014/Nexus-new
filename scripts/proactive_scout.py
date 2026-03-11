import subprocess
import os
import json
from datetime import datetime


def get_calendar_events():
    skill_script = (
        "/Users/jameschen/.openclaw/skills/apple-calendar/scripts/get_events.py"
    )
    try:
        raw = subprocess.check_output(["python3", skill_script]).decode("utf-8")
        return json.loads(raw).get("events", [])
    except:
        return []


def find_related_notes(keyword):
    try:
        # 在全庫搜尋相關筆記
        cmd = f"grep -rl '{keyword}' 知識庫 | head -n 2"
        paths = (
            subprocess.check_output(cmd, shell=True).decode("utf-8").strip().split("\n")
        )
        return [p for p in paths if p and ".md" in p]
    except:
        return []


def update_state_with_intelligence(events):
    state_path = "知識庫/01_Operations/STATE.yaml"
    weights = {"global": 1.0}
    pre_loaded = []

    for event in events:
        title = event["event"]
        # 1. 智慧預載邏輯
        related = find_related_notes(title[:4])
        for r in related:
            pre_loaded.append(
                f"[[{os.path.basename(r).replace('.md', '')}]] (Related to {title})"
            )

        # 2. 動態權重分配邏輯
        if any(k in title for k in ["教", "孩", "遊", "餐"]):
            weights["20_Family_Education"] = 2.0
            weights["Travel"] = 2.0
        if any(k in title for k in ["滑雪", "Ski", "板"]):
            weights["Skiing"] = 2.5

    # 寫入 STATE.yaml (模擬)
    with open(state_path, "a") as f:
        f.write(f"\n# --- Intelligence Injection {datetime.now().isoformat()} ---\n")
        f.write(f"predictive_context:\n  pre_loaded_insights: {pre_loaded}\n")
        f.write(f"dynamic_weights: {weights}\n")


def main():
    print("📡 Proactive Scout v4.0 (Full Intel) Starting...")
    events = get_calendar_events()
    update_state_with_intelligence(events)

    # 產出報告
    report_path = f"知識庫/01_Operations/Inbox/Scout_Report_{datetime.now().strftime('%Y_%m_%d')}.md"
    with open(report_path, "w") as f:
        f.write("# 🛡️ Proactive Scout 全效情報摘要\n\n")
        f.write("## 📅 今日行程\n")
        for e in events:
            f.write(f"- {e['event']} ({e['time']})\n")

        f.write("\n## 🔮 大腦預判與權重建議\n")
        f.write("- **建議 RAG 加權**: 請優先檢索與今日行程相關之領域。\n")

    print("✨ Full Intelligence Sync completed.")


if __name__ == "__main__":
    main()
