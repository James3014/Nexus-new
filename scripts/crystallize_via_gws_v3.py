#!/usr/bin/env -S uv run --script
# 🛡️ Codex-Verified: c075e8c (2026-03-06)
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "rich",
#     "pyyaml",
#     "python-dateutil",
# ]
# ///

import os
import sys
import re
import json
import subprocess
import datetime
import yaml
from dateutil import parser
from rich.console import Console
from rich.panel import Panel

# 🛡️ Nexus Integration
try:
    from nexus.services.gateway import BattlesuitGateway as LLMClient
except ImportError:
    # 支援獨立運行
    LLMClient = None

console = Console(force_terminal=True)

# ---------------------------------------------------------------------------
# [Codex-Verified: Lvl15-CRM-Crystallizer-v3.5 (Pagination Edition) (2026-03-06)]
# ---------------------------------------------------------------------------

BASE_DIR = "/Users/jameschen/Downloads/obsidian/知識庫/01_Projects/DIY_Customer_Success"
RAW_BASE = f"{BASE_DIR}/Raw_Data"
CASES_BASE = f"{BASE_DIR}/Cases"
STATE_FILE = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/STATE.yaml"

EXCLUDE_SUBJECTS = [
    "重要提醒",
    "保險資料",
    "上課提醒",
    "付款成功",
    "自動發送",
    "尚未填寫",
    "提醒通知",
    "資料不齊",
    "訂單已完成",
    "上課保險",
]
INTERACTION_KEYWORDS = [
    "訂單",
    "詢問",
    "取消",
    "教練",
    "退費",
    "改期",
    "場地",
    "修正",
    "有問題",
]


def get_season(date_str):
    try:
        dt = parser.parse(date_str)
        return (
            f"{dt.year}_{dt.year + 1}" if dt.month >= 7 else f"{dt.year - 1}_{dt.year}"
        )
    except:
        return "Unknown_Season"


def call_gws(resource, method, params=None):
    cmd = ["gws", "gmail", "users", resource, method, "--format", "json"]
    if params:
        cmd.extend(["--params", json.dumps(params)])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except:
        return None


def get_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return yaml.safe_load(f) or {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        yaml.dump(state, f)


def ask_gemini_for_crystallization(raw_json):
    msgs = raw_json.get("messages", [])
    t_id = raw_json.get("id", "N/A")
    summary_data = [
        {
            "from": next(
                (
                    h["value"]
                    for h in m.get("payload", {}).get("headers", [])
                    if h["name"].lower() == "from"
                ),
                "N/A",
            ),
            "snippet": m.get("snippet", ""),
        }
        for m in msgs
    ]

    prompt = f"分析 Gmail Thread。若純系統通知，則 skip: true。否則產出 YAML：skip, case_id, order_id, student_name, student_email, coach, trigger_event, urgency, sentiment, resolution_status, summary (20字摘要)。Thread ID: {t_id}\n{json.dumps(summary_data, ensure_ascii=False)}"
    
    # 🛡️ Nexus Battlesuit Gateway Integration
    if LLMClient:
        client = LLMClient(project_root=os.getcwd())
        data, raw_output = client.ask(prompt, "", phase="C")
        if data.get("status") == "FAIL": return None
        
        # 提取 YAML 部分 (相容原有邏輯)
        match = re.search(r"```yaml\s*(crystallized:.*?)\s*```", raw_output, re.DOTALL)
        if match:
            c_data = yaml.safe_load(match.group(1).strip()).get("crystallized")
            return "SKIP" if c_data and c_data.get("skip") is True else c_data
        return None
        
    try:
        # Fallback to direct CLI if Nexus is missing
        res = subprocess.run(
            ["gemini", "-p", "CRM 結晶化："],
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
        )
        match = re.search(r"```yaml\s*(crystallized:.*?)\s*```", res.stdout, re.DOTALL)
        if match:
            data = yaml.safe_load(match.group(1).strip()).get("crystallized")
            return "SKIP" if data and data.get("skip") is True else data
    except:
        return None


def process_thread(t):
    t_id = t["id"]
    thread_data = call_gws("threads", "get", {"userId": "me", "id": t_id})
    if not thread_data:
        return

    crystal = ask_gemini_for_crystallization(thread_data)
    if crystal == "SKIP" or not crystal:
        return

    season = get_season(
        next(
            (
                h["value"]
                for h in thread_data["messages"][0]["payload"]["headers"]
                if h["name"].lower() == "date"
            ),
            datetime.datetime.now().isoformat(),
        )
    )
    os.makedirs(f"{RAW_BASE}/{season}", exist_ok=True)
    os.makedirs(f"{CASES_BASE}/{season}", exist_ok=True)

    with open(f"{RAW_BASE}/{season}/{t_id}.json", "w", encoding="utf-8") as f:
        json.dump(thread_data, f, ensure_ascii=False, indent=2)

    case_id = str(crystal.get("case_id", t_id)).replace("/", "_")
    summary = crystal.pop("summary", "N/A")
    fm = yaml.dump(crystal, allow_unicode=True, sort_keys=False)

    with open(f"{CASES_BASE}/{season}/{case_id}.md", "w", encoding="utf-8") as f:
        f.write(
            f"---\n{fm}---\n\n# 📋 客服案例結晶: {case_id}\n\n## 📝 案例摘要\n{summary}\n\n## 🔗 連結\n- [Gmail](https://mail.google.com/mail/u/0/#inbox/{t_id})\n"
        )
    console.print(f"[green]✅ {case_id} 結晶完成[/green]")


def main():
    state = get_state()
    page_token = state.get("gmail_next_page_token")
    start_date = "2022/05/01"

    console.print(
        Panel(
            f"🚀 [bold cyan]啟動 v3.5 分頁結晶引擎 (Token: {page_token or 'Start'})[/bold cyan]"
        )
    )
    q = (
        f"after:{start_date} "
        + " ".join([f"-subject:{s}" for s in EXCLUDE_SUBJECTS])
        + f" ({' OR '.join(INTERACTION_KEYWORDS)})"
    )

    params = {"userId": "me", "q": q, "maxResults": 20}
    if page_token:
        params["pageToken"] = page_token

    res = call_gws("threads", "list", params)
    if not res:
        return

    threads = res.get("threads", [])
    for t in threads:
        process_thread(t)
        sys.stdout.flush()

    next_token = res.get("nextPageToken")
    if next_token:
        state["gmail_next_page_token"] = next_token
        save_state(state)
        console.print(f"[yellow]💾 進度已存檔，Next Page Token: {next_token}[/yellow]")


if __name__ == "__main__":
    main()
