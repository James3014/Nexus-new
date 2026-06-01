import pytest
from pathlib import Path
from unittest.mock import MagicMock
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.phases.reproduction import ReproductionPhase

def test_reproduction_phase_success():
    op = OperationalContext(
        instance_id="test", 
        repo_dir=Path("/tmp"), 
        problem_statement="bug",
        repro_script="print('bug')"
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    runner = MagicMock()
    runner.run_repro.return_value = (True, "physical evidence found")
    
    denoiser = MagicMock()
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser)
    result = phase.execute(ctx)
    
    assert result.success is True
    assert ctx.op.reproduced is True
    assert ctx.op.repro_evidence == "physical evidence found"

def test_reproduction_phase_env_failure():
    op = OperationalContext(
        instance_id="test", 
        repo_dir=Path("/tmp"), 
        problem_statement="bug",
        repro_script="print('bug')"
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    runner = MagicMock()
    runner.run_repro.return_value = (False, "ModuleNotFoundError: numpy")
    runner.is_environment_failure.return_value = True
    
    denoiser = MagicMock()
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser)
    result = phase.execute(ctx)
    
    assert result.success is False
    assert result.exit_layer == "repro_runner"
    assert result.error_reason == "REPRO_ENVIRONMENT_FAILURE"
