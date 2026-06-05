import pytest
from nexus.services.local_heal.pipeline import HealContext, HealPipeline
from nexus.services.local_heal.errors import PatchError, PatchErrorKind

def test_system_prompt_contains_anti_apology():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    sys_prompt = PromptBuilder.build_patch_system_prompt()
    
    assert "NO apologies" in sys_prompt
    assert "NO PLACEHOLDERS" in sys_prompt


def test_no_blocks_retry_increases_attempt_and_updates_prompt():
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
    from nexus.services.local_heal.errors import PatchError, PatchErrorKind
    
    orchestrator = HealOrchestrator(
        phases=[None, None, None, None, None],
        governance_gate=None
    )
    op = OperationalContext(
        instance_id="astropy-13398",
        problem_statement="test rotation_matrix",
        repo_dir=None,
        attempt=1,
        user_prompt="Original Prompt"
    )
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    error = PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="No blocks found")
    
    # 測試 _handle_retry
    updated_ctx = orchestrator._handle_retry(ctx, error)
    
    # 驗證 attempt 增加到 2
    assert updated_ctx.op.attempt == 2
    # 驗證 prompt 被更新且包含了錯誤提示
    assert "Original Prompt" in updated_ctx.op.user_prompt
    assert "CRITICAL WARNING" in updated_ctx.op.user_prompt


def test_system_prompt_contains_senior_engineering_rules():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    sys_prompt = PromptBuilder.build_patch_system_prompt()
    
    assert "SENIOR ENGINEERING RULES" in sys_prompt
    assert "AttributeError Safety" in sys_prompt
    assert "Case-Insensitive Protocol" in sys_prompt
