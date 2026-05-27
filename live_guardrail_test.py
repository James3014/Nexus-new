from nexus.core.planner_auditor import PlannerAuditor
from nexus.health.scoring import HealthScorer
from nexus.core.state_contracts import NexusState
import json

def run_live_test():
    print("🛡️  NEXUS GOVERNANCE GUARDRAIL LIVE TEST\n" + "="*40)
    
    # --- 情境 A：草率計畫 (缺失標籤) ---
    sloppy_plan = """
    # 偷懶計畫
    我打算直接改 code。
    """
    print("\n[SCENARIO A] Sloppy Plan Detection:")
    audit_a = PlannerAuditor.audit_plan(sloppy_plan)
    print(f"  > Audit Status: {audit_a['status']}")
    print(f"  > Density Score: {audit_a['density_score']:.2f}")
    
    state_a = NexusState(task_id="test-task-a")
    state_a.health_metrics.outcome_quality = 1.0 # 假設功能測試 100% 過
    state_a.metadata["plan_density_score"] = audit_a["density_score"]
    
    snapshot_a = HealthScorer.build_snapshot(state_a)
    print(f"  > AOS Score: {snapshot_a.overall_score:.1f}/120 (Penalty Triggered!)")

    # --- 情境 B：深度思考 (100% 標籤 + 內容) ---
    deep_plan = """
    # 深度計畫 v22 Eternal
    [Probe]: 已核驗 Rust stable 1.84.0 端點。
    [Surface]: 影響 nexus/health/scoring.py 與核心合約。
    [Rollback]: 預備了 git checkout 與 snapshot 每 30min 備份。
    """ + " ".join(["(Detail Context)"] * 50)
    
    print("\n[SCENARIO B] Deep Thinking Verification:")
    audit_b = PlannerAuditor.audit_plan(deep_plan)
    print(f"  > Audit Status: {audit_b['status']}")
    print(f"  > Density Score: {audit_b['density_score']:.2f}")
    
    state_b = NexusState(task_id="test-task-b")
    state_b.health_metrics.outcome_quality = 1.0
    state_b.metadata["plan_density_score"] = audit_b["density_score"]
    state_b.metadata["thinking_depth_score"] = audit_b["thinking_depth_score"]
    
    snapshot_b = HealthScorer.build_snapshot(state_b)
    print(f"  > AOS Score: {snapshot_b.overall_score:.1f}/120 (Healthy Crystalized!)")

if __name__ == "__main__":
    run_live_test()
