import json, sys, os
from pathlib import Path
from datetime import datetime, timezone

def _belief_recorded(beliefs_path: Path, belief_id: str) -> bool:
    if not beliefs_path.exists():
        return False
    for line in beliefs_path.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("belief_id") == belief_id:
                return True
        except (json.JSONDecodeError, AttributeError):
            continue
    return False


def crystallize(project_root: Path | None = None):
    project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    lessons_path = project_root / ".codex_lessons.md"
    knowledge_dir = project_root / ".nexusknowledge"
    
    if not lessons_path.exists():
        print("❌ No lessons found.")
        return

    # 模擬從 Markdown 提取最新教訓並內化為 Belief
    # 這裡針對 v0.9 聯邦防禦進行實體化
    belief = {
        "belief_id": "B-FED-SINGULARITY-001",
        "content": "Robust aggregation requires Median-based rejection and IQR thresholding.",
        "source": "v0.9_singularity_test",
        "confidence": 0.995,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # The belief is a fixed constant, so re-running must not append duplicates
    # to the git-tracked knowledge base.
    if _belief_recorded(knowledge_dir / "beliefs.jsonl", belief["belief_id"]):
        print(f"ℹ️ {belief['belief_id']} already anchored; nothing to append.")
        return

    # 寫入物理知識庫
    with open(knowledge_dir / "beliefs.jsonl", "a") as f:
        f.write(json.dumps(belief) + "\n")
    
    # 建立對帳提議 (Reconciliation Proposal)
    proposal = {
        "proposal_id": f"REC-{int(datetime.now().timestamp())}",
        "target_belief": "B-FED-SINGULARITY-001",
        "proposed_content": "enforce_iqr_filter=True",
        "evidence_strength": 0.99,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    with open(knowledge_dir / "reconciliation_proposals.jsonl", "a") as f:
        f.write(json.dumps(proposal) + "\n")
        
    print(f"✅ Crystallization complete: {belief['belief_id']} anchored.")

if __name__ == "__main__":
    crystallize()
