import json
import sys
from pathlib import Path
from nexus.engine.autonomic_router import AutonomicRouter
from nexus.core.state_contracts import NexusState

def test_v4_intelligence():
    print("🚀 [Nexus v4.0] Starting Automated Intelligence Acceptance Test...")
    project_root = Path.cwd()
    router = AutonomicRouter(project_root=str(project_root))
    
    # Target Policy: POL-AUTO-DETERMINISTIC-BUG-REMEDIATION
    # Condition: Execution of high-frequency automated bug fixes (e.g., OFF-001 pattern)
    task_desc = "Applying high-frequency automated bug fixes for OFF-001 patterns."
    state = NexusState(task_id="TEST-INTEL-AUTO-CHECK")
    forecast = {"est_tokens": 500, "roi_score": 0.9}
    
    print(f"🔍 Testing intent: '{task_desc}'")
    plan = router.route(task_desc, state, forecast)
    
    # A. Assert valid mode
    valid_modes = {"standard", "swarm", "research_first", "self_heal", "external_skill"}
    print(f"📊 Router Mode: {plan.mode}")
    assert plan.mode in valid_modes, f"Invalid router mode: {plan.mode}"
    
    # B. Assert policy hit
    target_pid = "POL-AUTO-DETERMINISTIC-BUG-REMEDIATION"
    print(f"⚖️ Matched Policies: {plan.matched_policies}")
    assert target_pid in plan.matched_policies, f"Failed to match critical policy: {target_pid}"
    
    print("\n✅ TEST PASSED: Autonomous Governance Bridge is operational.")
    return True

if __name__ == "__main__":
    try:
        success = test_v4_intelligence()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        sys.exit(1)
