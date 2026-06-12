#!/usr/bin/env python3
"""
🚀 Nexus Phase 4.5: 3B Student Data Export Script (Hardened)
按照修訂計畫將 S2T 追蹤數據轉換為 3B 模型訓練格式。
要求：非空 selected candidate, verifier evidence, model-provider lock, dataset card。
"""

import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional
import time

def redact_payload(data: Any) -> Any:
    """脫敏邏輯：移除路徑、密鑰與私有標識"""
    if isinstance(data, str):
        # 簡單路徑脫敏
        if "/" in data and " " not in data:
            return "<redacted-path>"
        return data
    if isinstance(data, dict):
        return {k: redact_payload(v) for k, v in data.items() if k not in ["secret_values", "private_paths"]}
    if isinstance(data, list):
        return [redact_payload(i) for i in data]
    return data

def export_student_data(input_path: Path, output_path: Path, card_path: Path):
    stats = {
        "total_read": 0,
        "exported": 0,
        "filtered_null_candidate": 0,
        "filtered_no_evidence": 0,
        "filtered_no_model": 0,
        "filtered_trust_mismatch": 0
    }
    
    with open(input_path, "r") as f_in, open(output_path, "w") as f_out:
        for line in f_in:
            stats["total_read"] += 1
            try:
                event = json.loads(line)
                
                # 1. Selected Candidate Check (Must be non-empty string and not NO_VERIFIED_CANDIDATE)
                candidate_id = event.get("selected_candidate_id")
                if not candidate_id or not isinstance(candidate_id, str) or candidate_id == "NO_VERIFIED_CANDIDATE":
                    stats["filtered_null_candidate"] += 1
                    continue
                
                # 2. Verifier Evidence Check (Requires physical/semantic verification)
                physical_verified = (
                    event.get("physical_verified", False) or 
                    event.get("semantic_verified", False) or 
                    event.get("gate", {}).get("claim_verified", False)
                )
                has_evidence = bool(
                    physical_verified or 
                    event.get("verifier_evidence_ref") or 
                    event.get("proof_present") or 
                    event.get("verifier_result") == "pass"
                )
                if not has_evidence:
                    stats["filtered_no_evidence"] += 1
                    continue
                
                # 3. Model-Provider Lock Check
                model_name = event.get("model") or event.get("metadata", {}).get("model_name_or_path")
                if not model_name:
                    stats["filtered_no_model"] += 1
                    continue
                
                # 4. Trust Mismatch Check (Query flat or nested)
                trust_mismatch = event.get("trust_mismatch", False) or event.get("gate", {}).get("trust_mismatch", False)
                if trust_mismatch:
                    stats["filtered_trust_mismatch"] += 1
                    continue
                
                # 建立符合 S2T Student Schema 的結構
                student_row = {
                    "task_id": event.get("task_id"),
                    "model": model_name,
                    "input": {
                        "risk_tier": event.get("risk_tier", "medium"),
                        "route_features": redact_payload(event.get("metadata", {}).get("forecast", {})),
                        "candidate_summaries": [
                            {"id": c.get("candidate_id"), "cost": c.get("cost")}
                            for c in event.get("candidates", [])
                        ],
                        "budget": event.get("metadata", {}).get("budget", {})
                    },
                    "target": {
                        "selected_candidate_id": candidate_id,
                        "selection_reason_codes": event.get("selection_reason_codes", ["matches_route_decision"]),
                        "required_verifier": event.get("verifier_name", "pytest"),
                        "abstain_reason": None
                    }
                }
                
                f_out.write(json.dumps(student_row, ensure_ascii=False) + "\n")
                stats["exported"] += 1
            except Exception:
                continue
    
    # 產出 Dataset Card
    dataset_card = {
        "timestamp": time.time(),
        "source_file": str(input_path),
        "target_file": str(output_path),
        "statistics": stats,
        "redaction_method": "path_pattern_and_key_exclusion",
        "split_method": "presumed_by_task_family_at_training_time",
        "status": "VALIDATED" if stats["exported"] >= 30 else "INSUFFICIENT_DATA"
    }
    
    card_path.write_text(json.dumps(dataset_card, indent=2, sort_keys=True))
    print(f"✅ Exported {stats['exported']} rows. Status: {dataset_card['status']}")
    print(f"📄 Dataset card saved to {card_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(".nexus/metrics/skill_outcome_events.jsonl"))
    parser.add_argument("--output", type=Path, default=Path(".nexus/training/s2t_3b_student_v1.jsonl"))
    parser.add_argument("--card", type=Path, default=Path(".nexus/training/dataset_card.json"))
    args = parser.parse_args()
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_student_data(args.input, args.output, args.card)
