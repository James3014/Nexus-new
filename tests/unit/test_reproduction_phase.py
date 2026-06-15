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
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, ollama_generate_fn=MagicMock())
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
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, ollama_generate_fn=MagicMock())
    result = phase.execute(ctx)
    
    assert result.success is False
    assert result.exit_layer == "repro_runner"
    assert result.failure_reason == "REPRO_ENVIRONMENT_FAILURE"

def test_reproduction_phase_provider_error():
    op = OperationalContext(
        instance_id="test",
        repo_dir=Path("/tmp"),
        problem_statement="bug",
        repro_script=""
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    runner = MagicMock()
    denoiser = MagicMock()
    llm_client = MagicMock()
    # Mock timeout exception which map to MODEL_TIMEOUT, or other exceptions mapping to MODEL_PROVIDER_ERROR
    llm_client.generate.side_effect = Exception("connection error")
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, llm_client=llm_client)
    result = phase.execute(ctx)
    
    assert result.success is False
    assert result.failure_reason == "MODEL_PROVIDER_ERROR"
    assert "MODEL_PROVIDER_ERROR" in ctx.op.model_decisions[-1]["status"]

def test_reproduction_phase_empty_response():
    op = OperationalContext(
        instance_id="test",
        repo_dir=Path("/tmp"),
        problem_statement="bug",
        repro_script=""
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    runner = MagicMock()
    denoiser = MagicMock()
    llm_client = MagicMock()
    llm_client.generate.return_value = ""
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, llm_client=llm_client)
    result = phase.execute(ctx)
    
    assert result.success is False
    assert result.failure_reason == "NO_REPRO_SCRIPT"
    assert ctx.op.model_decisions[-1]["status"] == "NO_REPRO_SCRIPT"

def test_reproduction_phase_env_denoise_failed():
    op = OperationalContext(
        instance_id="test",
        repo_dir=Path("/tmp"),
        problem_statement="bug",
        repro_script="print('bug')",
        auto_heal_enabled=True
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    runner = MagicMock()
    runner.run_repro.return_value = (False, "ModuleNotFoundError: numpy")
    runner.is_environment_failure.return_value = True
    
    denoiser = MagicMock()
    denoise_result = MagicMock()
    del denoise_result.to_receipt
    denoise_result.attempted = True
    denoise_result.succeeded = False
    denoise_result.reason = "could not install"
    denoiser.prepare_from_evidence.return_value = denoise_result
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, ollama_generate_fn=MagicMock())
    result = phase.execute(ctx)
    
    assert result.success is False
    assert result.failure_reason == "REPRO_ENVIRONMENT_FAILURE"
    assert ctx.op.env_denoise.get("attempted") is True
    assert ctx.op.env_denoise.get("succeeded") is False

def test_reproduction_phase_skip_reproduction():
    op = OperationalContext(
        instance_id="test",
        repo_dir=Path("/tmp"),
        problem_statement="long bug description",
        repro_script="",
        skip_reproduction=True
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    runner = MagicMock()
    denoiser = MagicMock()
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, ollama_generate_fn=MagicMock())
    result = phase.execute(ctx)
    
    assert result.success is True
    assert ctx.op.reproduced is True
    assert ctx.op.repro_evidence == "long bug description"
