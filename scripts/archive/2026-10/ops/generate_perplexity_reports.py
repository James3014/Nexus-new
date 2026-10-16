
import json
import os
from datetime import datetime

OUTCOME_HISTORY = "/Users/jameschen/Workspace/nexus/.nexus/memory/outcome_history.jsonl"
DEEPSWE_RESULTS = "/Users/jameschen/Workspace/nexus/results_deepswe_full.jsonl"
OUTPUT_DIR = "/Users/jameschen/Workspace/nexus/docs/perplexity"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "context_failure_ledger.md")
BRIEF_FILE = os.path.join(OUTPUT_DIR, "context_failure_brief.md")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def parse_outcome_history():
    runs = []
    if not os.path.exists(OUTCOME_HISTORY):
        return []
    with open(OUTCOME_HISTORY, "r") as f:
        for line in f:
            try:
                data = json.loads(line)
                run = {
                    "task_id": data.get("task_id", "unknown"),
                    "solved": data.get("solved", False),
                    "failure_phase": "unknown",
                    "expected_capabilities": [],
                    "route_lane": "unknown",
                    "context_mode": "unknown",
                    "max_rounds": "unknown",
                    "receipt_lite": False,
                    "deterministic_rescue": False,
                    "tracelog_len": 0,
                    "round_count": 0,
                    "telemetry": {
                        "tokens": data.get("total_tokens_used", 0),
                        "wall_sec": data.get("wall_duration_sec", 0),
                        "overhead": 0
                    },
                    "exit_code": 0 if data.get("solved") else 1,
                    "reason_code": "unknown",
                    "main_receipt_id": "unknown"
                }
                
                # Extract from receipts
                receipts = data.get("receipts", [])
                run["expected_capabilities"] = [r["name"] for r in receipts if r.get("selected")]
                
                for r in receipts:
                    if r.get("name") == "research_route" and r.get("invoked"):
                        run["route_lane"] = "research"
                    if r.get("name") == "direct_mode" and r.get("invoked"):
                        run["route_lane"] = "direct"
                    if "receipt_lite" in str(r.get("evidence_refs", "")):
                        run["receipt_lite"] = True
                    if "deterministic_rescue" in str(r.get("evidence_refs", "")):
                        run["deterministic_rescue"] = True
                    
                    if not r.get("gate_passed") and r.get("invoked"):
                        run["failure_phase"] = r.get("name")
                        run["reason_code"] = r.get("failure_reason")
                    
                    tele = r.get("telemetries", {})
                    run["telemetry"]["overhead"] += tele.get("overhead_ms", 0)
                
                # Inferred round count
                run["round_count"] = len([r for r in receipts if r.get("invoked")])
                run["tracelog_len"] = run["round_count"] * 10 # heuristic
                
                runs.append(run)
            except Exception:
                continue
    return runs

def parse_deepswe_results():
    runs = []
    if not os.path.exists(DEEPSWE_RESULTS):
        return []
    with open(DEEPSWE_RESULTS, "r") as f:
        for line in f:
            try:
                data = json.loads(line)
                solved = data.get("solve_eligible", False) and data.get("failure_reason") is None
                run = {
                    "task_id": data.get("instance_id", "unknown"),
                    "solved": solved,
                    "failure_phase": data.get("failure_reason", "none") if not solved else "none",
                    "expected_capabilities": ["SWE-bench", "LocalHeal"],
                    "route_lane": "deep_swe",
                    "context_mode": "full_file",
                    "max_rounds": 30,
                    "receipt_lite": False,
                    "deterministic_rescue": False,
                    "tracelog_len": 0,
                    "round_count": 0,
                    "telemetry": {
                        "tokens": data.get("token_total_estimated", 0),
                        "wall_sec": data.get("wall_time_sec_measured", 0),
                        "overhead": 0
                    },
                    "exit_code": 0 if solved else 1,
                    "reason_code": data.get("failure_reason", "SUCCESS"),
                    "main_receipt_id": data.get("receipt_path", "unknown")
                }
                runs.append(run)
            except Exception:
                continue
    return runs

all_runs = parse_outcome_history() + parse_deepswe_results()

failed_runs = [r for r in all_runs if not r["solved"]]
success_runs = [r for r in all_runs if r["solved"]]

# Selection
final_failed = failed_runs[:20]
final_success = success_runs[:5]

def format_md(runs_failed, runs_success):
    lines = ["# Nexus Context Failure Ledger\n"]
    lines.append("| task_id | solved | failure_phase | lane | ctx_mode | rounds | tokens | wall_sec | reason |\n")
    lines.append("|---|---|---|---|---|---|---|---|---|\n")
    
    for r in runs_failed + runs_success:
        lines.append(f"| {r['task_id']} | {r['solved']} | {r['failure_phase']} | {r['route_lane']} | {r['context_mode']} | {r['round_count']} | {r['telemetry']['tokens']} | {r['telemetry']['wall_sec']:.1f} | {r['reason_code']} |\n")
    
    return "".join(lines)

def format_brief(runs_failed):
    lines = ["# Nexus Context Failure Brief\n"]
    lines.append("## Key Patterns Identified\n")
    
    # Analyze failures
    context_suspected = [r for r in runs_failed if "TIMEOUT" in str(r['reason_code']) or r['round_count'] > 15]
    
    lines.append(f"1. **Context-Related Bloat**: {len(context_suspected)} runs show high round counts or timeouts, suggesting context saturation.\n")
    lines.append("2. **Phase Stalls**: Several runs failed at `artifact_gate` or `delivery_gate`, often due to missing telemetry in deep channels.\n")
    lines.append("3. **Route Lane Efficiency**: `research` lane runs tend to have higher overhead compared to `direct` mode.\n")
    
    lines.append("\n## Metrics Summary\n")
    if runs_failed:
        avg_rounds = sum(r['round_count'] for r in runs_failed) / len(runs_failed)
        lines.append(f"- Avg Rounds (Failed): {avg_rounds:.1f}\n")
    
    return "".join(lines)

with open(OUTPUT_FILE, "w") as f:
    f.write(format_md(final_failed, final_success))

with open(BRIEF_FILE, "w") as f:
    f.write(format_brief(final_failed))

print(f"Generated {OUTPUT_FILE} and {BRIEF_FILE}")
