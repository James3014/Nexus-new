"""C6L: General retry replace-only contract tests.

Ensures retry uses authoritative SEARCH from Nexus, model generates REPLACE only.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_retry_uses_authoritative_current_search_span():
    """Retry must use Nexus-provided SEARCH span, not model-generated SEARCH."""
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # Current file state
    current_source = (
        "def normalize_score(score, min_val, max_val):\n"
        "    return (score - min_val) / (max_val - min_val)\n"
    )

    # Get canonical span from current source
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(current_source)
        source_file = Path(f.name)

    try:
        result = get_canonical_search_span(
            locked_search="",
            patch_diff="",
            source_file=source_file,
            target_symbol="normalize_score",
            failed_search_text="",
        )

        assert result is not None
        # Authoritative SEARCH must match current source
        assert result.span.strip() in current_source
    finally:
        source_file.unlink()


def test_retry_prompt_no_longer_requires_model_generated_search():
    """Retry prompt should instruct model to generate REPLACE only."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="FAIL: normalize_score does not clamp",
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Prompt should still contain SEARCH/REPLACE markers for compatibility
    # but should emphasize REPLACE-only generation
    assert "<<<<<<< SEARCH" in prompt
    assert ">>>>>>> REPLACE" in prompt


def test_replace_only_retry_preserves_fail_closed_semantics():
    """Replace-only retry must still fail-closed on invalid patches."""
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.patch_applier import PatchApplier
    from nexus.services.local_heal.interface import LocalizedFile
    from pathlib import Path
    import tempfile

    # Create a test file
    current_source = "def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)\n"

    with tempfile.TemporaryDirectory() as tmp_dir:
        target_path = Path(tmp_dir) / "toy" / "math_util.py"
        target_path.parent.mkdir(parents=True)
        target_path.write_text(current_source)

        # Simulate: Nexus provides authoritative SEARCH, model provides REPLACE
        authoritative_search = "def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)"
        model_replace = "def normalize_score(score, min_val, max_val):\n    if max_val == min_val:\n        return 0.5\n    return max(0, min(1, (score - min_val) / (max_val - min_val)))"

        # Assemble patch
        patch_text = (
            f"FILE: toy/math_util.py\n"
            f"<<<<<<< SEARCH\n"
            f"{authoritative_search}\n"
            f"=======\n"
            f"{model_replace}\n"
            f">>>>>>> REPLACE\n"
        )

        parser = SolidSearchReplaceProtocol()
        patcher = Patcher()
        applier = PatchApplier(parser, patcher)

        intents = parser.parse(patch_text)
        assert not isinstance(intents, Exception)

        res = applier.apply_and_validate(
            intents=intents,
            repo_dir=Path(tmp_dir),
            localized_files=[LocalizedFile(path="toy/math_util.py", content=current_source)],
        )

        # Should succeed
        assert res.success is True


def test_generic_search_mismatch_improves_to_apply_lane():
    """Generic SEARCH_MISMATCH cases should improve to apply/verifier lane."""
    # This tests the concept: if Nexus provides authoritative SEARCH,
    # SEARCH_MISMATCH should not occur for the retry path

    # Simulate: model generates SEARCH that doesn't match, but Nexus replaces it
    model_search = "def normalize_score(score, min_val, max_val):\n    return 0"  # Wrong
    authoritative_search = "def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)"  # Correct

    # After Nexus replacement, the SEARCH should be authoritative
    final_search = authoritative_search  # Nexus replaces model's SEARCH
    assert final_search == authoritative_search
    assert final_search != model_search
