import json
import hashlib
import random
from pathlib import Path

def redact_task_id(task_id: str) -> str:
    """Apply one-way hash to task_id to mask original name."""
    if not task_id:
        return ""
    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:16]

def get_split(task_id: str) -> str:
    """Use deterministic hash for splits to avoid duplicate leakage."""
    h = int(hashlib.md5(task_id.encode()).hexdigest(), 16) % 100
    if h < 80:
        return "train"
    elif h < 90:
        return "dev"
    else:
        return "test"

def generate_families():
    rows = []
    
    # 1. regular_pass (baseline behavior)
    for i in range(500):
        tid = f"task-regular-{i}"
        rows.append({
            "task_id": redact_task_id(tid),
            "source_family": "regular_pass",
            "split": get_split(tid),
            "input": {
                "risk_tier": "medium",
                "route_features": {"complexity": "low"},
                "candidate_summaries": [
                    {"id": f"cand-{i}-0", "cost": 0.01, "verifier_result": "fail"},
                    {"id": f"cand-{i}-1", "cost": 0.02, "verifier_result": "pass"}
                ],
                "budget": {"max_cost": 0.05}
            },
            "target": {
                "selected_candidate_id": f"cand-{i}-1",
                "selection_reason_codes": ["verifier_failed_candidate_excluded", "within_budget_limit"],
                "required_verifier": "pytest",
                "abstain_reason": None
            }
        })
        
    # 2. top_1_fail (Top-1 failed candidate -> choose 2nd)
    for i in range(200):
        tid = f"task-top1fail-{i}"
        rows.append({
            "task_id": redact_task_id(tid),
            "source_family": "top_1_fail",
            "split": get_split(tid),
            "input": {
                "risk_tier": "medium",
                "route_features": {"complexity": "medium"},
                "candidate_summaries": [
                    {"id": f"cand-{i}-top", "cost": 0.01, "verifier_result": "fail"},
                    {"id": f"cand-{i}-alt", "cost": 0.02, "verifier_result": "pass"}
                ],
                "budget": {"max_cost": 0.05}
            },
            "target": {
                "selected_candidate_id": f"cand-{i}-alt",
                "selection_reason_codes": ["top1_failed_fallback_successful"],
                "required_verifier": "pytest",
                "abstain_reason": None
            }
        })

    # 3. gate_rejection (Abstain family - all fail)
    for i in range(100):
        tid = f"task-gaterej-{i}"
        rows.append({
            "task_id": redact_task_id(tid),
            "source_family": "gate_rejection",
            "split": get_split(tid),
            "input": {
                "risk_tier": "high",
                "route_features": {"complexity": "high"},
                "candidate_summaries": [
                    {"id": f"cand-{i}-0", "cost": 0.01, "verifier_result": "fail"},
                    {"id": f"cand-{i}-1", "cost": 0.02, "verifier_result": "fail"}
                ],
                "budget": {"max_cost": 0.05}
            },
            "target": {
                "selected_candidate_id": None,
                "selection_reason_codes": [],
                "required_verifier": None,
                "abstain_reason": "all_candidates_failed_verifier"
            }
        })

    # 4. over_cost_route (Abstain family - over budget)
    for i in range(100):
        tid = f"task-overcost-{i}"
        rows.append({
            "task_id": redact_task_id(tid),
            "source_family": "over_cost_route",
            "split": get_split(tid),
            "input": {
                "risk_tier": "low",
                "route_features": {"complexity": "low"},
                "candidate_summaries": [
                    {"id": f"cand-{i}-0", "cost": 0.08, "verifier_result": "pass"}
                ],
                "budget": {"max_cost": 0.05}
            },
            "target": {
                "selected_candidate_id": None,
                "selection_reason_codes": [],
                "required_verifier": None,
                "abstain_reason": "no_valid_candidate_within_budget"
            }
        })

    return rows

def main():
    project_root = Path(__file__).resolve().parents[2]
    dest_path = project_root / ".nexus" / "training" / "s2t_3b_student_v2.jsonl"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    rows = generate_families()
    
    # Deterministic shuffle
    random.seed(42)
    random.shuffle(rows)
    
    counts = {"train": 0, "dev": 0, "test": 0}
    with open(dest_path, "w", encoding="utf-8") as f:
        for r in rows:
            counts[r["split"]] += 1
            f.write(json.dumps(r) + "\n")
            
    print(f"✅ V2 Dataset Generated: {dest_path}")
    print(f"Total Rows: {len(rows)}")
    print(f"Splits: {counts}")

if __name__ == "__main__":
    main()
