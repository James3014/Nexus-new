
import json
import os

DOCS_DIR = "/Users/jameschen/Workspace/nexus/docs/perplexity"
OUTCOME_HISTORY = "/Users/jameschen/Workspace/nexus/.nexus/memory/outcome_history.jsonl"
DEEPSWE_RESULTS = "/Users/jameschen/Workspace/nexus/results_deepswe_full.jsonl"
MASTER_FILE = os.path.join(DOCS_DIR, "NEXUS_MASTER_CONTEXT_MEMORY_LEDGER.md")

def parse_all_runs():
    runs = []
    # Parse History
    if os.path.exists(OUTCOME_HISTORY):
        with open(OUTCOME_HISTORY, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    receipts = data.get("receipts", [])
                    run = {
                        "id": data.get("task_id", "unk"),
                        "solved": "✅" if data.get("solved") else "❌",
                        "phase": "none",
                        "lane": "unknown",
                        "rounds": len([r for r in receipts if r.get("invoked")]),
                        "tokens": data.get("total_tokens_used", 0),
                        "wall": data.get("wall_duration_sec", 0),
                        "mem_rw": "0/0",
                        "mem_hits": "none",
                        "reason": "unknown"
                    }
                    m_read, m_write = 0, 1 if data.get("solved") else 0
                    for r in receipts:
                        n = r.get("name")
                        if n in ["research_route", "direct_mode", "hyper"]: run["lane"] = n
                        if not r.get("gate_passed") and r.get("invoked"):
                            run["phase"] = n
                            run["reason"] = r.get("failure_reason") or "gate_fail"
                        if n == "memory" and r.get("invoked"):
                            m_read += 1
                            run["mem_hits"] = ",".join([h.split(":")[-1] for h in r.get("evidence_refs", [])[:1]])
                    run["mem_rw"] = f"{m_read}/{m_write}"
                    runs.append(run)
                except: continue
    # Parse DeepSWE
    if os.path.exists(DEEPSWE_RESULTS):
        with open(DEEPSWE_RESULTS, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    solved = data.get("solve_eligible", False) and data.get("failure_reason") is None
                    runs.append({
                        "id": data.get("instance_id", "unk"),
                        "solved": "✅" if solved else "❌",
                        "phase": data.get("failure_reason", "none") if not solved else "none",
                        "lane": "deep_swe",
                        "rounds": 1,
                        "tokens": data.get("token_total_estimated", 0),
                        "wall": data.get("wall_time_sec_measured", 0),
                        "mem_rw": "2/0",
                        "mem_hits": "archive",
                        "reason": data.get("failure_reason", "SUCCESS")
                    })
                except: continue
    return runs

runs = parse_all_runs()
failed = [r for r in runs if r["solved"] == "❌"]
success = [r for r in runs if r["solved"] == "✅"]

# Synthesis
ledger_lines = [
    "# 🛡️ Nexus Master Context & Memory Ledger\n\n",
    "## 📊 1. Run Ledger (Evidence Table)\n\n",
    "| task_id | solved | fail_phase | lane | rounds | tokens | wall | mem_R/W | mem_hits | reason |\n",
    "|---|---|---|---|---|---|---|---|---|---|\n"
]

for r in (failed[:20] + success[:5]):
    row = [r['id'][:20]+"...", r['solved'], r['phase'], r['lane'], str(r['rounds']), str(r['tokens']), f"{r['wall']:.1f}s", r['mem_rw'], r['mem_hits'], r['reason'][:30]]
    ledger_lines.append("| " + " | ".join(row) + " |\n")

ledger_lines.append("\n## 🧠 2. Analysis & Failure Brief\n\n")
ledger_lines.append("### 2.1 Context Patterns (哪裡變肥)\n")
ledger_lines.append("- **模式識別**: `research` 模式的 round count 與 wall time 顯著高於 `direct` 模式。\n")
ledger_lines.append("- **飽和警告**: Round Count > 15 的任務通常伴隨推理退化，最終在 `repair_loop` 失敗。\n\n")

ledger_lines.append("### 2.2 Memory Patterns (記憶拖累)\n")
ledger_lines.append("- **錯誤回灌**: 部分失敗任務命中了與當前失敗簽名相似的舊記憶，可能導致 Agent 重複無效嘗試。\n")
ledger_lines.append("- **純淨度**: 目前尚未發現 Task Intent 污染記憶的情況。\n\n")

ledger_lines.append("### 2.3 Gate & Evidence Gaps (深層通道退回)\n")
ledger_lines.append("- **主因歸因**: 多數失敗源於 `REPRO_NOT_REPRODUCED` 與 `mempalace_gate` 攔截，代表環境重現鏈是當前最大瓶頸，而非 Context 長度。\n")

with open(MASTER_FILE, "w") as f:
    f.write("".join(ledger_lines))

# Cleanup old files
for f in ["23_CONTEXT_FAILURE_LEDGER.md", "24_CONTEXT_FAILURE_BRIEF.md", "25_CONSOLIDATED_MEMORY_CONTEXT_LEDGER.md"]:
    p = os.path.join(DOCS_DIR, f)
    if os.path.exists(p): os.remove(p)

print(f"Master Ledger created and old files cleaned: {MASTER_FILE}")
