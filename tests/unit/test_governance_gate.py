import pytest
from pathlib import Path
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate

def test_governance_gate_policy_match():
    op = OperationalContext(instance_id="t1", repo_dir=Path("/tmp"), problem_statement="p")
    gov = GovernanceContext(expected_stop_layer="env_resolver", expected_reason_family="env_noise")
    ctx = HealContext(op=op, gov=gov)
    
    # Simulate a policy block
    ctx.gov.gate_exit = "env_resolver"
    ctx.op.failure_reason = "ENV_VIOLATION"
    
    GovernanceGate.audit(ctx)
    
    assert ctx.gov.stop_layer_matched is True
    assert ctx.gov.family_matched is True
    assert ctx.gov.actual_reason_family == "env_noise"

def test_governance_gate_solved_match():
    op = OperationalContext(instance_id="t2", repo_dir=Path("/tmp"), problem_statement="p")
    gov = GovernanceContext(expected_stop_layer="verification", expected_reason_family="SOLVED")
    ctx = HealContext(op=op, gov=gov)
    
    ctx.gov.gate_exit = "verification"
    ctx.op.solve_eligible = True
    
    GovernanceGate.audit(ctx)
    
    assert ctx.gov.stop_layer_matched is True
    assert ctx.gov.family_matched is True
