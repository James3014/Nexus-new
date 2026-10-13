# eaeb94b2f (P0-4) replaced the 14-rule hardening prompt with the SOURCE ANCHORING contract
# plus one few-shot example. The removed wording must stay absent.
_REMOVED_WORDING = (
    "NO apologies",
    "NO PLACEHOLDERS",
    "SENIOR ENGINEERING RULES",
    "AttributeError Safety",
    "Case-Insensitive Protocol",
    "Fail loudly",
)


def _prompts() -> dict[str, str]:
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    return {
        "default": PromptBuilder.build_patch_system_prompt(),
        "small_local": PromptBuilder.build_patch_system_prompt("qwen2.5-coder:7b"),
        "interleaved": PromptBuilder.build_patch_system_prompt(interleaved=True),
    }


def test_system_prompt_contains_anti_apology():
    prompts = _prompts()
    for kind, sys_prompt in prompts.items():
        assert "NO apologies" not in sys_prompt, kind
        assert "NO PLACEHOLDERS" not in sys_prompt, kind
    # Current hardening contract: output-only SEARCH/REPLACE, no prose, no placeholders.
    assert "Output ONLY SEARCH/REPLACE blocks" in prompts["default"]
    assert "no explanations" in prompts["default"]
    assert "No placeholders ('# ...', '... code ...')" in prompts["default"]
    assert "No prose outside the block" in prompts["small_local"]


def test_no_blocks_retry_increases_attempt_and_updates_prompt():
    from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
    from nexus.services.local_heal.errors import PatchError, PatchErrorKind
    from nexus.services.local_heal.orchestrator import HealOrchestrator

    orchestrator = HealOrchestrator(phases=[None, None, None, None, None], governance_gate=None)
    op = OperationalContext(
        instance_id="astropy-13398",
        problem_statement="test rotation_matrix",
        repo_dir=None,
        attempt=1,
        user_prompt="Original Prompt",
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
    prompts = _prompts()
    for kind, sys_prompt in prompts.items():
        for removed in _REMOVED_WORDING:
            assert removed not in sys_prompt, f"{kind}: {removed!r} was removed in eaeb94b2f"
        # Current contract: SOURCE ANCHORING replaces the SENIOR ENGINEERING RULES block.
        assert "SOURCE ANCHORING" in sys_prompt, kind
        assert "SEARCH may NOT change anything." in sys_prompt, kind
    assert "Use hasattr()/getattr() for dynamic access." in prompts["default"]
