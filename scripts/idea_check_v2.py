#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import sys
import json
import os
import re
from parallel_spawner import run_parallel_agents
from idea_decomposer import decompose_idea

REPORT_DIR = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/Brain_Reports"


def reality_check_v2(idea):
    print(f"🚀 [Muse-Core Lvl 13] 啟動平行子代理集群，對 '{idea}' 進行深度現實檢查...")
    tasks = decompose_idea(idea)
    results = run_parallel_agents(tasks, session_prefix="idea_cluster")

    report_content = f"# 🔬 現實檢查報告：{idea}\n\n"
    report_content += "> **生成方式**: Sub-Agent Spawning (4 平行集群)\n\n"
    headers = ["📚 大腦關聯", "🐙 GitHub 參考", "🌏 全球情報", "⚖️ 現實評估"]

    for i, header in enumerate(headers):
        report_content += f"## {header}\n"
        res = results[i]  # 此處已確保 results 與 headers 順序一致
        if res and res["success"]:
            try:
                match = re.search(r"\{.*\}", res["output"], re.DOTALL)
                data = json.loads(match.group(0)) if match else {}
                payloads = data.get("result", {}).get("payloads") or data.get(
                    "payloads", []
                )
                text = payloads[0].get("text", "無內容") if payloads else "無內容"
                report_content += f"{text}\n\n"
            except:
                report_content += f"{res['output']}\n\n"
        else:
            report_content += f"❌ 執行失敗: {res.get('error', '未知錯誤')}\n\n"

    os.makedirs(REPORT_DIR, exist_ok=True)
    filename = f"Reality_Check_{re.sub(r'[^a-zA-Z0-9]', '_', idea)[:30]}.md"
    filepath = os.path.join(REPORT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"✨ 全量現實檢查完成！報告已產出：{filepath}")
    return filepath


if __name__ == "__main__":
    idea = sys.argv[1] if len(sys.argv) > 1 else "test idea"
    reality_check_v2(idea)
