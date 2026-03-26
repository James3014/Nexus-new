import os
import json
from wisdom_distiller import distill_wisdom

# [SOTA 10/10] Wisdom Distillation Privacy Audit
# Verification based on Sir's expert "Symbolic Generalization" criteria.

def test_privacy():
    print("// Nexus-Distiller Test: Starting Privacy & Anonymization Audit...")

    # 1. Tenant A (Opt-in) Distillation
    print("// Nexus-Distiller Test: Step 1 - Distilling Tenant A (Opt-in)...")
    raw_result_a = {
        "type": "adapter_lesson",
        "fragility_type": "SCHEMA_UI_DIRECT_BINDING (table.questions)",
        "fix_template_used": "adapter_v1_for_tenant_A",
        "success_rate": 0.95,
        "lesson": "Secrets: sk-tenant-a-super-secret-key-123456789. Paths: /Users/jameschen/Workspace/nexus/workspaces/A/src/main.rs. Binding table.questions is risky."
    }
    
    crystal_a = distill_wisdom("A", raw_result_a)
    
    print(f"// Crystal A Lesson: {crystal_a.get('lesson')}")
    
    # Assertions for Anonymization
    assert "sk-REDACTED" in crystal_a.get("lesson")
    assert "/workspace/tenant/" in crystal_a.get("lesson")
    assert "table.data_table" in crystal_a.get("lesson")
    assert "sk-tenant-a-super-secret-key-123456789" not in crystal_a.get("lesson")
    assert "/workspaces/A/" not in crystal_a.get("lesson")
    assert "table.questions" not in crystal_a.get("lesson")
    assert crystal_a.get("fix_template_used") == "adapter_v1_for_tenant_REDACTED" 
    
    # 2. Tenant B (Opt-out) Distillation
    print("// Nexus-Distiller Test: Step 2 - Distilling Tenant B (Opt-out)...")
    crystal_b = distill_wisdom("B", raw_result_a)
    assert crystal_b is None
    print("// Nexus-Distiller Test: Tenant B correctly withheld wisdom.")

    # 3. Global Hub Verification
    print("// Nexus-Distiller Test: Step 3 - Verifying Global Wisdom Hub...")
    with open("/Users/jameschen/Workspace/nexus/global_crystals.jsonl", "r") as f:
        hub_content = f.read()
        if "sk-tenant-a-super-secret-key" in hub_content:
            print("!! PRIVACY BREACH: Raw secret found in Global Hub!")
            assert False
        else:
            print("// Nexus-Distiller Test: Global Hub is CLEAN. Wisdom successfully distilled.")

    print("// Nexus-Distiller Test: Phase 3 Wisdom Distillation Audit SUCCESS. Singularity 10/10.")

if __name__ == "__main__":
    test_privacy()
