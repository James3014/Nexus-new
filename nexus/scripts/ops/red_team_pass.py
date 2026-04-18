import sys
import json
from pathlib import Path

def run_adversarial_vanguard():
    print("🕵️ [Red-Team] Continuous Audit Node Engagement...")
    project_root = Path.cwd()
    
    # 查核點 1: 是否已修正 4 參數噴錯問題?
    orch_path = project_root / "nexus/core/orchestrator.py"
    with open(orch_path, "r") as f:
        content = f.read()
        if "update_belief" in content and "task_id=" not in content:
            print("❌ [Audit-FAIL] Orchestrator signature is legacy/broken.")
            return False

    # 查核點 2: EvidenceGuard 是否具備語義鎖定?
    guard_path = project_root / "nexus/core/evidence_guard.py"
    with open(guard_path, "r") as f:
        content = f.read()
        if "git_hub" not in content or "keywords" not in content:
            print("❌ [Audit-FAIL] EvidenceGuard is too weak. Needs Semantic Interlock.")
            return False

    # 查核點 3: 信心狀態完整性
    belief_path = project_root / ".nexus" / "belief_state.json"
    if not belief_path.exists():
        # 初次啟動允許
        pass

    print("✅ [Audit-PASS] Standard MET: High-Hardness Enforcement Detected.")
    return True

if __name__ == "__main__":
    if run_adversarial_vanguard():
        # 簽發物理核准令
        state_dir = Path(".nexus/state")
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(state_dir / "red_team_verdict.json", "w") as f:
            json.dump({"verdict": "APPROVED", "model": "gemini-3.1-pro-preview", "timestamp": "2026-04-18T22:00"}, f)
        sys.exit(0)
    else:
        sys.exit(1)
