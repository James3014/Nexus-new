import json
from pathlib import Path

def generate_dataset():
    project_root = Path(__file__).resolve().parents[2]
    dest_path = project_root / ".nexus" / "training" / "s2t_heldout_harder_tasks.jsonl"
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    # 建立 35 筆較難的 heldout 任務
    for i in range(35):
        # harder task 的特徵：有 3 個候選人，包含高低分、以及一個 verifier failed 被排除的候選
        task = {
            "task_id": f"hard-task-{i}",
            "split": "heldout",
            "model": "gemini-3-flash-preview",
            "input": {
                "risk_tier": "high" if i % 3 == 0 else "medium",
                "route_features": {
                    "complexity": "high" if i % 2 == 0 else "medium",
                    "file_count": 5 + i
                },
                "candidate_summaries": [
                    {"id": f"cand-fail-{i}", "cost": 0.05, "verifier_result": "fail"},
                    {"id": f"cand-pass-lowcost-{i}", "cost": 0.01, "verifier_result": "pass"},
                    {"id": f"cand-pass-highcost-{i}", "cost": 0.08, "verifier_result": "pass"}
                ],
                "budget": {"max_cost": 0.06}
            },
            "target": {
                # 最佳候選應排除 failed 的，且符合 budget 預算限制下成本最低的 pass 候選
                "selected_candidate_id": f"cand-pass-lowcost-{i}",
                "selection_reason_codes": [
                    "verifier_failed_candidate_excluded",
                    "within_budget_limit",
                    "cost_effective_pass_candidate"
                ],
                "required_verifier": "claim_gate",
                "abstain_reason": None
            }
        }
        rows.append(task)

    with open(dest_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"✅ Heldout Harder Tasks dataset generated with {len(rows)} rows at {dest_path}")

if __name__ == "__main__":
    generate_dataset()
