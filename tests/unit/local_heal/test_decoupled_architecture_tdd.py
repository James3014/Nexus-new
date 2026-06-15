import pytest
from pathlib import Path
from typing import Dict, Any, Tuple, List

from nexus.services.local_heal.reasoning_router import ReasoningRouter
from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient
from nexus.services.local_heal.interface import (
    PlanningInput, PlanningOutput, PatchSynthesisInput,
    ReproductionInput, ReproductionOutput,
    LocalizationInput, LocalizationOutput,
    VerificationInput, VerificationOutput
)
from nexus.services.local_heal.phases.planning import PlanningPhase
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.phases.reproduction import ReproductionPhase
from nexus.services.local_heal.phases.localization import LocalizationPhase
from nexus.services.local_heal.phases.verification import VerificationPhase
from nexus.services.local_heal.granular_localizer import LocalizationBundle

# 1. Mock LLM client implementation
class DummyLLMClient(ILLMClient):
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout: int | None = None,
        options: Dict[str, Any] | None = None,
        api_type: str = "generate"
    ) -> str:
        self.calls.append({
            "system": system_prompt,
            "user": user_prompt,
            "model": model,
            "timeout": timeout,
            "options": options,
            "api_type": api_type
        })
        return self.response_text


# 2. Mock program entities
class StubReproductionRunner:
    def __init__(self, success: bool, evidence: str):
        self.success = success
        self.evidence = evidence
        self.python_executable = "python3"

    def run_repro(self, script_content: str) -> Tuple[bool, str]:
        return self.success, self.evidence

    def is_environment_failure(self, evidence: str) -> bool:
        return "ModuleNotFoundError" in evidence


class StubEnvDenoiser:
    def __init__(self, succeeded: bool):
        self.succeeded = succeeded
        self.python_executable = "/bin/python"

    def prepare_from_evidence(self, evidence: str):
        class DenoiseResult:
            def __init__(self, succ, py):
                self.succeeded = succ
                self.python_executable = py
            def to_receipt(self):
                return {"succeeded": self.succeeded}
        return DenoiseResult(self.succeeded, self.python_executable)


class StubLocalizer:
    def rank_files(self, query: str, repo_dir: Path, search_symbols: List[str] = None):
        return [(1.0, {"path": "foo.py", "content": "class Foo: pass"})]

    def localize(self, path: str, content: str, query: str) -> LocalizationBundle:
        return LocalizationBundle(
            file_path=path,
            primary_snippet=content,
            slice_reason="Surgical slice",
            confidence=0.9
        )


class StubBudgetManager:
    def enforce_hard_limit(self, files: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        return files


class StubTestResult:
    def __init__(self, passed: bool):
        self.passed = passed


class StubEvaluationGate:
    def __init__(self, passed: bool):
        self.passed = passed

    def run_visible_tests(self, commands: List[List[str]]) -> List[Any]:
        return [StubTestResult(self.passed)]

    def run_hidden_verifier(self, args: List[str]) -> List[Any]:
        return [StubTestResult(self.passed)]

    def get_redacted_report(self, visible: List[Any], hidden: List[Any]) -> str:
        return "Verification report."


# 3. Unit Tests
def test_reasoning_router_defaults():
    router = ReasoningRouter()
    mode_astropy = router.route("Consider fixing structured array ndarray mixin in astropy", Path("/repo/astropy"))
    assert mode_astropy == "ALGEBRAIC"

    mode_django = router.route("Fix query filter bug in django", Path("/repo/django"))
    assert mode_django == "INTUITIVE"


def test_reasoning_router_custom_rule():
    router = ReasoningRouter()
    router.register_rule(lambda stmt, path: "ALGEBRAIC" if "matrix" in stmt else None)

    mode = router.route("Fix matrix multiplication performance", Path("/repo/math"))
    assert mode == "ALGEBRAIC"


def test_ollama_llm_client_reflection():
    calls = []
    def generate_fn_with_extra(sys, usr, model=None, timeout=None, options=None):
        calls.append({"model": model, "timeout": timeout, "options": options})
        return "reflect_ok"

    client = OllamaLLMClient(generate_fn_with_extra)
    res = client.generate("sys", "usr", model="qwen", timeout=120, options={"temp": 0})
    
    assert res == "reflect_ok"
    assert len(calls) == 1
    assert calls[0]["model"] == "qwen"
    assert calls[0]["timeout"] == 120
    assert calls[0]["options"] == {"temp": 0}


def test_planning_phase_stateless_run():
    response_json = '{"search_symbols": ["FooClass"], "repair_strategy": "Fix foo.", "violated_invariants": []}'
    llm_client = DummyLLMClient(response_json)
    
    planner = Planner(llm_client=llm_client)
    phase = PlanningPhase(planner=planner)
    
    inp = PlanningInput(
        problem_statement="Fix bug in FooClass",
        repro_evidence="AssertionError",
        repo_dir=Path("/tmp/foo"),
        reasoning_mode="INTUITIVE"
    )
    
    out = phase.run(inp)
    assert out.success is True
    # P0-5: DeterministicSymbolExtractor merges symbols from problem + evidence;
    # "FooClass" from problem and "AssertionError" from evidence are both valid.
    assert "FooClass" in out.plan["search_symbols"]
    assert len(llm_client.calls) == 1
    assert llm_client.calls[0]["model"] == "qwen2.5-coder:7b"


def test_reproduction_phase_stateless_run():
    runner = StubReproductionRunner(success=True, evidence="Assertion failed successfully.")
    denoiser = StubEnvDenoiser(succeeded=False)
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser)

    inp = ReproductionInput(
        instance_id="task-1",
        repo_dir=Path("/tmp/repo"),
        problem_statement="Failure issue",
        repro_script="assert False",
        python_executable="python3"
    )

    out = phase.run(inp)
    assert out.success is True
    assert out.reproduced is True
    assert out.repro_evidence == "Assertion failed successfully."


def test_localization_phase_stateless_run():
    localizer = StubLocalizer()
    budget_mgr = StubBudgetManager()
    phase = LocalizationPhase(localizer=localizer, budget_manager=budget_mgr)

    inp = LocalizationInput(
        problem_statement="Repair bug",
        repro_evidence="Error",
        repo_dir=Path("/tmp/repo"),
        plan={"search_symbols": ["Foo"]}
    )

    out = phase.run(inp)
    assert out.success is True
    assert len(out.localized_files) == 1
    assert out.localized_files[0][0] == "foo.py"


def test_verification_phase_stateless_run(tmp_path):
    eval_gate = StubEvaluationGate(passed=True)
    phase = VerificationPhase(eval_gate=eval_gate, hidden_required=True)

    inp = VerificationInput(
        instance_id="task-1",
        repo_dir=tmp_path,
        problem_statement="Problem",
        final_patch="diff ...",
        repro_script="print('OK')",
        python_executable="python3"
    )

    out = phase.run(inp)
    assert out.success is True
    assert out.hidden_verifier_passed is True
    assert out.solve_eligible is True


# ─── P0 Fix Tests ─────────────────────────────────────────────────────────────

def test_skip_reproduction_uses_problem_statement_as_evidence():
    """P0-1: When skip_reproduction=True, ReproductionPhase must bypass LLM
    and use problem_statement[:3000] as repro_evidence."""
    from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext

    runner = StubReproductionRunner(success=False, evidence="")
    denoiser = StubEnvDenoiser(succeeded=False)
    phase = ReproductionPhase(repro_runner=runner, env_denoiser=denoiser)

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-skip",
            repo_dir=Path("/tmp"),
            problem_statement="Fix the `NdarrayMixin` structured array bug.",
            skip_reproduction=True,
        ),
        gov=GovernanceContext()
    )

    result = phase.execute(ctx)
    assert result.success is True
    assert ctx.op.reproduced is True
    assert "NdarrayMixin" in ctx.op.repro_evidence


def test_deterministic_symbol_extractor_backtick():
    """P0-5: DeterministicSymbolExtractor must find backtick-enclosed identifiers."""
    from nexus.services.local_heal.planner import DeterministicSymbolExtractor

    problem = "The `NdarrayMixin` class in `astropy.table.column` fails when `Column` receives structured data."
    symbols = DeterministicSymbolExtractor.extract(problem)

    assert "NdarrayMixin" in symbols
    assert "Column" in symbols


def test_deterministic_symbol_extractor_camelcase():
    """P0-5: CamelCase class names in prose should be extracted."""
    from nexus.services.local_heal.planner import DeterministicSymbolExtractor

    problem = "QuerySet.filter() raises AttributeError when using TemporalModel with TimezoneMixin."
    symbols = DeterministicSymbolExtractor.extract(problem)

    assert "QuerySet" in symbols
    assert "AttributeError" in symbols


def test_deterministic_symbol_extractor_no_noise():
    """P0-5: Common Python keywords should be filtered out."""
    from nexus.services.local_heal.planner import DeterministicSymbolExtractor

    problem = "import return class def self true false none"
    symbols = DeterministicSymbolExtractor.extract(problem)

    assert "import" not in symbols
    assert "return" not in symbols
    assert "self" not in symbols


def test_context_window_expansion():
    """P0-2: 7B model must have num_ctx=16384 and num_predict=4096."""
    from nexus.engine.local_model_policy import ModelProfile

    opts_7b = ModelProfile.get_options("qwen2.5-coder:7b", attempt=1)
    assert opts_7b["num_ctx"] == 16384
    assert opts_7b["num_predict"] == 4096
    assert opts_7b["temperature"] == 0.0

    opts_14b = ModelProfile.get_options("qwen2.5-coder:14b", attempt=1)
    assert opts_14b["num_ctx"] == 32768
    assert opts_14b["num_predict"] == 8192


def test_temperature_scaling_on_retry():
    """P1-1: Temperature must increase on retry attempts to break failure loops."""
    from nexus.engine.local_model_policy import ModelProfile

    opts_attempt1 = ModelProfile.get_options("qwen2.5-coder:7b", attempt=1)
    opts_attempt2 = ModelProfile.get_options("qwen2.5-coder:7b", attempt=2)
    opts_attempt3 = ModelProfile.get_options("qwen2.5-coder:7b", attempt=3)

    assert opts_attempt1["temperature"] == 0.0
    assert opts_attempt2["temperature"] > 0.0
    assert opts_attempt3["temperature"] > opts_attempt2["temperature"]
    assert opts_attempt3["temperature"] <= 0.4  # capped


def test_cross_file_search_fallback(tmp_path):
    """P0-3b: When model declares wrong FILE but SEARCH matches a localized file,
    PatchSynthesisPhase must auto-correct the file path and apply the patch."""
    # Create two files: column.py (wrong, declared) and table.py (correct, has code)
    column_py = tmp_path / "column.py"
    table_py = tmp_path / "table.py"
    column_py.write_text("class Column:\n    pass\n", encoding="utf-8")
    table_py.write_text(
        "def _convert_data(data):\n    if isinstance(data, int):\n        return float(data)\n    return data\n",
        encoding="utf-8"
    )

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()

    # LLM output declares FILE: column.py but SEARCH block matches table.py
    llm_response = (
        "FILE: column.py\n"
        "<<<<<<< SEARCH\n"
        "    if isinstance(data, int):\n"
        "        return float(data)\n"
        "=======\n"
        "    if isinstance(data, (int, str)):\n"
        "        return float(data)\n"
        ">>>>>>> REPLACE\n"
    )
    llm_client = DummyLLMClient(llm_response)

    phase = PatchSynthesisPhase(parser=parser, patcher=patcher, llm_client=llm_client)
    inp = PatchSynthesisInput(
        instance_id="test-crossfile",
        problem_statement="Fix data conversion",
        repro_evidence="TypeError",
        plan={"search_symbols": ["_convert_data"], "repair_strategy": "fix", "violated_invariants": []},
        localized_files=[("column.py", column_py.read_text()), ("table.py", table_py.read_text())],
        repo_dir=tmp_path,
        reasoning_mode="INTUITIVE",
        attempt=1,
        max_tries=3,
    )

    out = phase.run(inp)
    # Should succeed by auto-correcting to table.py
    assert out.success is True, f"Expected cross-file fallback to succeed, got: {out.failure_reason}"
    # table.py should be patched
    patched = table_py.read_text()
    assert "(int, str)" in patched


def test_slim_prompt_for_7b():
    """P1-2: PromptBuilder.build_patch_system_prompt must return a slim prompt
    containing '<path>' and shorter description if the model name contains '7b'."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    slim_prompt = PromptBuilder.build_patch_system_prompt("qwen2.5-coder:7b")
    full_prompt = PromptBuilder.build_patch_system_prompt("qwen2.5-coder:14b")

    # Slim prompt should be noticeably shorter than full prompt
    assert len(slim_prompt) < len(full_prompt)
    assert "FILE: <path>" in slim_prompt
    assert "CHARACTER-FOR-CHARACTER" not in slim_prompt
    assert "hasattr()/getattr()" not in slim_prompt
    
    # Check that full prompt still has the detailed rules
    assert "FILE: <path/to/file.py>" in full_prompt
    assert "CHARACTER-FOR-CHARACTER" in full_prompt


def test_legacy_heal_context_skip_reproduction():
    """P0-1 End-to-End: Legacy HealContext wrapper must support skip_reproduction
    and pass it properly when converted to V2 operational context."""
    from nexus.services.local_heal.pipeline import HealContext

    ctx = HealContext(
        instance_id="test-legacy-skip",
        repo_dir=Path("/tmp"),
        problem_statement="Fix it."
    )
    ctx.skip_reproduction = True

    v2_ctx = ctx.to_v2()
    assert v2_ctx.op.skip_reproduction is True

def test_local_model_policy_routing():
    from nexus.engine.local_model_policy import LocalModelPolicy
    import os

    # planning -> 7B
    decision = LocalModelPolicy.select_model(task_type="repair", phase="planning", context={})
    assert decision["model"] == "qwen2.5-coder:7b"
    assert "scaffolding" in decision["reason_code"]

    # reproduction -> 7B
    decision = LocalModelPolicy.select_model(task_type="repair", phase="reproduction", context={})
    assert decision["model"] == "qwen2.5-coder:7b"
    assert "repro" in decision["reason_code"]

    # first mechanical patch -> 7B
    decision = LocalModelPolicy.select_model(task_type="repair", phase="patch", context={"attempt": 1, "reasoning_mode": "INTUITIVE"})
    assert decision["model"] == "qwen2.5-coder:7b"
    assert "mechanical" in decision["reason_code"]

    # algebraic patch -> 14B
    decision = LocalModelPolicy.select_model(task_type="repair", phase="patch", context={"attempt": 1, "reasoning_mode": "ALGEBRAIC"})
    assert decision["model"] == "qwen2.5-coder:14b"
    assert "algebraic" in decision["reason_code"]

    # retry patch -> 14B by default
    decision = LocalModelPolicy.select_model(task_type="repair", phase="patch", context={"attempt": 2})
    assert decision["model"] == "qwen2.5-coder:14b"
    assert "retry_precision_escalation_ollama" == decision["reason_code"]

    # NEXUS_DISABLE_14B_RETRY=1 -> retry stays 7B
    os.environ["NEXUS_DISABLE_14B_RETRY"] = "1"
    try:
        decision = LocalModelPolicy.select_model(task_type="repair", phase="patch", context={"attempt": 2})
        assert decision["model"] == "qwen2.5-coder:7b"
        assert "fallback_to_7b" in decision["reason_code"]
    finally:
        del os.environ["NEXUS_DISABLE_14B_RETRY"]
