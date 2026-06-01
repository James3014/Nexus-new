import pytest
from pathlib import Path
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext

def test_heal_context_composition():
    op = OperationalContext(
        instance_id="test-1",
        repo_dir=Path("/tmp"),
        problem_statement="fix it"
    )
    gov = GovernanceContext(
        expected_stop_layer="env_resolver",
        expected_reason_family="env_noise"
    )
    ctx = HealContext(op=op, gov=gov)
    
    assert ctx.instance_id == "test-1"
    assert ctx.expected_stop_layer == "env_resolver"
    assert ctx.problem_statement == "fix it"
    
    # Test mutation
    ctx.op.reproduced = True
    assert ctx.reproduced is True

def test_governance_matching_logic():
    # This will be tested once we have the GovernanceGate or equivalent
    pass
