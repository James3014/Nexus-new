from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.interface import LocalizedFile, PatchSynthesisOutput, PhaseResult
from nexus.services.local_heal.latency_ledger import LatencyLedger
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol


class DummyLLMClient:
    def __init__(self, response_text: str):
        self.response_text = response_text

    def generate(self, **kwargs):
        return self.response_text


def test_patch_synthesis_execute_forwards_search_mismatch_error_metadata(tmp_path: Path):
    phase = PatchSynthesisPhase(
        parser=SolidSearchReplaceProtocol(),
        patcher=Patcher(),
        llm_client=DummyLLMClient(""),
    )

    mismatch = PatchError(
        kind=PatchErrorKind.SEARCH_MISMATCH,
        message="SEARCH mismatch in math.py",
        file_path="math.py",
        failed_search_text="def add(a, b):\n    return a + b\n",
        telemetry={
            "canonical_span": {
                "auto_corrected": False,
                "canonical_search_hash": "abc123",
                "correction": "fuzzy_candidate:line_trim:0.98",
            },
            "closest_match": {
                "resolved_span": "L1-L2",
            },
            "requires_authority": True,
        },
    )

    output = PatchSynthesisOutput(
        success=False,
        final_patch="",
        model_decisions=[],
        error_reason="SEARCH_MISMATCH",
        errors=[mismatch],
        preflight_telemetry={"output_class": "VALID_SEARCH_REPLACE"},
    )

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-search-metadata",
            repo_dir=tmp_path,
            problem_statement="fix add",
            localized_files=[LocalizedFile(path="math.py", content="def add(a, b):\n    return a - b\n")],
        ),
        gov=GovernanceContext(),
    )

    phase.run = lambda input_data: output
    result = phase.execute(ctx)

    assert result.success is False
    assert result.error_metadata is not None
    assert result.error_metadata["file_path"] == "math.py"
    assert result.error_metadata["failed_search_text"].startswith("def add")
    assert result.error_metadata["requires_authority"] is True
    assert result.error_metadata["canonical_span"]["canonical_search_hash"] == "abc123"
    assert result.error_metadata["closest_match_info"]["resolved_span"] == "L1-L2"


def test_orchestrator_search_mismatch_retry_uses_patch_failure_structured_packet(tmp_path: Path):
    ctx = HealContext(
        op=OperationalContext(
            instance_id="orchestrator-search-mismatch",
            repo_dir=tmp_path,
            problem_statement="fix add",
            user_prompt="Fix the add function",
            localized_files=[LocalizedFile(path="math.py", content="def add(a, b):\n    return a - b\n")],
        ),
        gov=GovernanceContext(),
    )
    ctx.op.plan = SimpleNamespace(
        search_symbols=["add"],
        verifier_command="pytest tests/test_math.py",
    )

    res = PhaseResult(
        success=False,
        failure_reason="SEARCH_MISMATCH",
        error_metadata={
            "file_path": "math.py",
            "failed_search_text": "def add(a, b):\n    return a + b\n",
            "canonical_span": {
                "canonical_search_hash": "abc123",
                "canonical_line_start": 12,
            },
            "closest_match_info": {
                "resolved_span": "def add(a, b):\n    return a - b\n",
            },
        },
    )

    orchestrator = HealOrchestrator(phases=[], governance_gate=GovernanceGate())
    should_retry = orchestrator._handle_patch_failure(
        ctx,
        res,
        LatencyLedger(task_id="t_search_packet", instance_id="orchestrator-search-mismatch"),
    )

    assert should_retry is True
    assert ctx.op.attempt == 2
    assert "STRUCTURED FAILURE DETAILS" in ctx.op.user_prompt
    assert "[LOCATION] math.py:12" in ctx.op.user_prompt
    assert "[REPRO] pytest tests/test_math.py" in ctx.op.user_prompt
    assert "[SOURCE]" in ctx.op.user_prompt
    assert "return a - b" in ctx.op.user_prompt


def test_patch_synthesis_execute_forwards_syntax_error_metadata(tmp_path: Path):
    phase = PatchSynthesisPhase(
        parser=SolidSearchReplaceProtocol(),
        patcher=Patcher(),
        llm_client=DummyLLMClient(""),
    )

    syntax_error = PatchError(
        kind=PatchErrorKind.SYNTAX_ERROR,
        message="expected an indented block after 'if' statement on line 5",
        file_path="math.py",
        failed_search_text="if value:\n    return value\n",
        telemetry={
            "preflight_checks": [
                {
                    "check": "replace_syntax",
                    "passed": False,
                    "syntax_error_line": 6,
                    "syntax_error_offset": 5,
                    "syntax_error_msg": "expected an indented block after 'if' statement",
                    "indentation_base": "'    '",
                }
            ]
        },
    )

    output = PatchSynthesisOutput(
        success=False,
        final_patch="",
        model_decisions=[],
        error_reason="REPLACE_SYNTAX_ERROR:expected an indented block after 'if' statement on line 5",
        errors=[syntax_error],
        preflight_telemetry={"output_class": "VALID_SEARCH_REPLACE"},
    )

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-syntax-metadata",
            repo_dir=tmp_path,
            problem_statement="fix syntax",
            localized_files=[LocalizedFile(path="math.py", content="if value:\n    return value\n")],
        ),
        gov=GovernanceContext(),
    )

    phase.run = lambda input_data: output
    result = phase.execute(ctx)

    assert result.success is False
    assert result.error_metadata is not None
    assert result.error_metadata["file_path"] == "math.py"
    assert result.error_metadata["syntax_error_line"] == 6
    assert result.error_metadata["syntax_error_offset"] == 5
    assert "indented block" in result.error_metadata["syntax_error_msg"]
    assert result.error_metadata["failed_search_text"].startswith("if value:")


def test_orchestrator_syntax_error_retry_uses_patch_failure_structured_packet(tmp_path: Path):
    ctx = HealContext(
        op=OperationalContext(
            instance_id="orchestrator-syntax-mismatch",
            repo_dir=tmp_path,
            problem_statement="fix syntax",
            user_prompt="Fix the indentation bug",
            localized_files=[LocalizedFile(path="math.py", content="if value:\n    return value\n")],
        ),
        gov=GovernanceContext(),
    )
    ctx.op.plan = SimpleNamespace(
        search_symbols=["value"],
        verifier_command="pytest tests/test_math.py",
    )

    res = PhaseResult(
        success=False,
        failure_reason="REPLACE_SYNTAX_ERROR:expected an indented block after 'if' statement on line 5",
        error_metadata={
            "file_path": "math.py",
            "failed_search_text": "if value:\n    return value\n",
            "syntax_error_line": 6,
            "syntax_error_offset": 5,
            "syntax_error_msg": "expected an indented block after 'if' statement",
        },
    )

    orchestrator = HealOrchestrator(phases=[], governance_gate=GovernanceGate())
    should_retry = orchestrator._handle_patch_failure(
        ctx,
        res,
        LatencyLedger(task_id="t_syntax_packet", instance_id="orchestrator-syntax-mismatch"),
    )

    assert should_retry is True
    assert ctx.op.attempt == 2
    assert "STRUCTURED FAILURE DETAILS" in ctx.op.user_prompt
    assert "[LOCATION] math.py:6" in ctx.op.user_prompt
    assert "[REPRO] pytest tests/test_math.py" in ctx.op.user_prompt
    assert "[SOURCE]" in ctx.op.user_prompt
    assert "Keep the SEARCH block EXACTLY the same" in ctx.op.user_prompt


def test_orchestrator_verification_failure_preserves_pre_verification_patch(tmp_path: Path):
    ctx = HealContext(
        op=OperationalContext(
            instance_id="orchestrator-verification-preserve",
            repo_dir=tmp_path,
            problem_statement="fix logic",
            user_prompt="Fix the failing behavior",
            final_patch="--- a/math.py\n+++ b/math.py\n@@\n-return 0\n+return 1\n",
        ),
        gov=GovernanceContext(),
    )
    ctx.op.attempt = 2

    res = PhaseResult(
        success=False,
        failure_reason="VERIFICATION_FAILED",
    )

    orchestrator = HealOrchestrator(phases=[], governance_gate=GovernanceGate())
    orchestrator._handle_verification_failure(ctx, res)

    assert ctx.op.final_patch == ""
    assert ctx.op.failure_reason == "LOGIC_REGRESSION:VERIFICATION_FAILED"
    assert ctx.op.pre_verification_final_patch.startswith("--- a/math.py")
