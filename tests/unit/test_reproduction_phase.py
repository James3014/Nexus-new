import hashlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
from nexus.services.local_heal.interface import ReproductionInput, ReproductionProvenance
from nexus.services.local_heal.phases.reproduction import ReproductionPhase
from nexus.services.local_heal.reproduction import ReproductionRunner


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
    runner.last_exit_status = 7
    runner.last_reason_code = "physical_fail"
    runner.last_command = ("python3", "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = (
        f"HEAD={'b' * 40};WORKSPACE_SHA256={'d' * 64}", True
    )
    
    denoiser = MagicMock()
    
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser, ollama_generate_fn=MagicMock())
    result = phase.execute(ctx)
    
    assert result.success is True
    assert ctx.op.reproduced is True
    assert ctx.op.repro_evidence == "physical evidence found"
    assert isinstance(ctx.op.reproduction_provenance, ReproductionProvenance)
    assert ctx.op.reproduction_provenance.source_kind == "physical"
    assert ctx.op.reproduction_provenance.physical is True
    assert ctx.op.reproduction_provenance.exit_status == 7
    assert ctx.op.reproduction_provenance.reason_code == "physical_fail"
    assert ctx.op.reproduction_provenance.command == ("python3", "reproduce_bug.py")
    assert ctx.op.reproduction_provenance.script_sha256 == "a" * 64
    assert ctx.op.reproduction_provenance.source_sha256
    assert ctx.op.reproduction_provenance.evidence_sha256

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
    assert ctx.op.reproduction_provenance.source_kind == "skip"
    assert ctx.op.reproduction_provenance.reason_code == "skip_reproduction"
    assert ctx.op.reproduction_provenance.physical is False


def test_reproduction_phase_pre_supplied_evidence_is_not_physical():
    op = OperationalContext(
        instance_id="test", repo_dir=Path("/tmp"), problem_statement="bug",
        repro_evidence="copied evidence",
    )
    ctx = HealContext(op=op, gov=GovernanceContext())
    result = ReproductionPhase(MagicMock(), MagicMock()).execute(ctx)
    assert result.success is True
    assert ctx.op.reproduction_provenance.source_kind == "pre_supplied"
    assert ctx.op.reproduction_provenance.reason_code == "pre_supplied_evidence"
    assert ctx.op.reproduction_provenance.physical is False


def test_reproduction_phase_descriptive_evidence_is_not_physical():
    phase = ReproductionPhase(MagicMock(), MagicMock())
    output = phase.run(ReproductionInput("test", Path("/tmp"), "description", "", "python3"))
    assert output.provenance.source_kind == "descriptive"
    assert output.provenance.reason_code == "descriptive_evidence"
    assert output.provenance.physical is False


def test_reproduction_phase_unbound_source_cannot_be_physical():
    runner = MagicMock()
    runner.run_repro.return_value = (True, "bug evidence")
    runner.last_exit_status = 3
    runner.last_reason_code = "physical_fail"
    runner.last_command = ("python3", "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = ("", False)
    op = OperationalContext(
        instance_id="test", repo_dir=Path("/tmp"), problem_statement="bug",
        repro_script="raise AssertionError('bug')",
    )
    ctx = HealContext(op=op, gov=GovernanceContext())
    ReproductionPhase(runner, MagicMock()).execute(ctx)
    assert ctx.op.reproduction_provenance.source_kind == "physical"
    assert ctx.op.reproduction_provenance.physical is False
    assert ctx.op.reproduction_provenance.reason_code == "unbound_source"


def test_reproduction_phase_missing_exit_status_cannot_be_physical():
    runner = MagicMock()
    runner.run_repro.return_value = (False, "timed out")
    runner.last_exit_status = None
    runner.last_reason_code = "execution_timeout"
    runner.last_command = ("python3", "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = (
        f"HEAD={'b' * 40};WORKSPACE_SHA256={'d' * 64}", True
    )
    op = OperationalContext(
        instance_id="test", repo_dir=Path("/tmp"), problem_statement="bug",
        repro_script="assert False",
    )
    ctx = HealContext(op=op, gov=GovernanceContext())
    ReproductionPhase(runner, MagicMock()).execute(ctx)
    assert ctx.op.reproduction_provenance.physical is False
    assert ctx.op.reproduction_provenance.reason_code == "execution_timeout"


def test_reproduction_phase_bool_exit_status_cannot_be_physical():
    runner = MagicMock()
    runner.run_repro.return_value = (True, "bug evidence")
    runner.last_exit_status = True
    runner.last_reason_code = "physical_fail"
    runner.last_command = ("python3", "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = (
        f"HEAD={'b' * 40};WORKSPACE_SHA256={'d' * 64}", True
    )
    op = OperationalContext(
        instance_id="test", repo_dir=Path("/tmp"), problem_statement="bug",
        repro_script="assert False",
    )
    ctx = HealContext(op=op, gov=GovernanceContext())
    ReproductionPhase(runner, MagicMock()).execute(ctx)
    assert ctx.op.reproduction_provenance.physical is False
    assert ctx.op.reproduction_provenance.reason_code == "missing_exit_status"


def test_reproduction_phase_arbitrary_crash_cannot_be_physical():
    runner = MagicMock()
    runner.run_repro.return_value = (False, "RuntimeError: unrelated crash")
    runner.last_exit_status = 9
    runner.last_reason_code = "unclassified_nonzero_exit"
    runner.last_command = ("python3", "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = (
        f"HEAD={'b' * 40};WORKSPACE_SHA256={'d' * 64}", True
    )
    op = OperationalContext(
        instance_id="test", repo_dir=Path("/tmp"), problem_statement="bug",
        repro_script="raise RuntimeError('unrelated crash')",
    )
    ctx = HealContext(op=op, gov=GovernanceContext())
    ReproductionPhase(runner, MagicMock()).execute(ctx)
    assert ctx.op.reproduction_provenance.physical is False
    assert ctx.op.reproduction_provenance.reason_code == "unclassified_nonzero_exit"


def test_reproduction_phase_rejects_dormant_assert_runtime_crash(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    script = "if False:\n    assert False, 'dormant'\nraise RuntimeError('unrelated crash')"
    output = ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", tmp_path, "bug", script, sys.executable)
    )
    assert output.success is False
    assert output.provenance.physical is False
    assert output.provenance.exit_status == 1
    assert output.provenance.reason_code == "unclassified_nonzero_exit"


def test_reproduction_phase_ignores_forged_failure_marker(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    script = (
        "import hashlib, json, sys\n"
        "token = hashlib.sha256(_nexus_source.encode('utf-8')).hexdigest()\n"
        "payload = {'exception_type': 'AssertionError', 'filename': "
        "'nexus_repro_contract.py', 'lineno': 1, 'exit_code': None}\n"
        "print('__NEXUS_REPRO_FAILURE__:' + token + ':' + "
        "json.dumps(payload, sort_keys=True), file=sys.stderr)\n"
        "raise RuntimeError('unrelated crash')\n"
    )
    output = ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", tmp_path, "bug", script, sys.executable)
    )
    assert output.success is False
    assert output.provenance.physical is False
    assert output.provenance.reason_code == "unclassified_nonzero_exit"


def test_reproduction_phase_rejects_bool_system_exit(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    script = "import sys\nprint('ERROR: bool exit')\nsys.exit(True)"
    output = ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", tmp_path, "bug", script, sys.executable)
    )
    assert output.success is False
    assert output.provenance.physical is False
    assert output.provenance.exit_status == 1
    assert output.provenance.reason_code == "unclassified_nonzero_exit"


def test_reproduction_phase_binds_actual_executed_script_and_command(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    output = ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", tmp_path, "bug", "assert False", sys.executable)
    )
    provenance = output.provenance
    assert output.success is True
    assert provenance.physical is True
    assert provenance.reason_code == "physical_fail"
    assert provenance.command == (sys.executable, "reproduce_bug.py")
    assert provenance.exit_status == 1
    assert provenance.source_identity.startswith("HEAD=")
    assert provenance.script_sha256 == hashlib.sha256(
        (tmp_path / "reproduce_bug.py").read_bytes()
    ).hexdigest()
