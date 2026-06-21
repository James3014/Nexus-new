"""P14: Candidate Generation Rework Tests"""
import hashlib
import pytest
from nexus.services.local_heal.candidate_generation import (
    ReplacementSpanKind,
    CandidateParserStatus,
    CandidatePatchStatus,
    NarrowSpanCandidate,
    CandidateGenerationResult,
    is_abstain,
    classify_replacement_span,
    is_span_acceptable,
    is_duplicate,
    build_narrow_span_prompt,
    build_intent_prompt,
    generate_narrow_span_candidates,
)


# ─── ABSTAIN Tests ───────────────────────────────────────────────────────────

def test_abstain_exact():
    """ABSTAIN should be detected exactly."""
    assert is_abstain("ABSTAIN") is True
    assert is_abstain("  ABSTAIN  ") is True
    assert is_abstain("\nABSTAIN\n") is True


def test_abstain_case_insensitive():
    """ABSTAIN should be case-insensitive."""
    assert is_abstain("abstain") is True
    assert is_abstain("Abstain") is True


def test_abstain_not_code():
    """ABSTAIN should not match code that happens to contain the word."""
    assert is_abstain("return ABSTAIN") is False
    assert is_abstain("ABSTAIN if x else something") is False
    assert is_abstain("# ABSTAIN") is False


# ─── Span Classification Tests ───────────────────────────────────────────────

def test_classify_single_return():
    """Single return should be classified as SINGLE_RETURN."""
    kind = classify_replacement_span("return x + 1", "old_code")
    assert kind == ReplacementSpanKind.SINGLE_RETURN


def test_classify_single_assignment():
    """Single assignment should be classified as SINGLE_ASSIGNMENT."""
    kind = classify_replacement_span("result = x + 1", "old_code")
    assert kind == ReplacementSpanKind.SINGLE_ASSIGNMENT


def test_classify_localized_block():
    """Small block should be classified as LOCALIZED_BLOCK."""
    code = "if x:\n    return 1\nelse:\n    return 2"
    kind = classify_replacement_span(code, "old_code")
    assert kind == ReplacementSpanKind.LOCALIZED_BLOCK


def test_classify_broad_method():
    """Large block should be classified as BROAD_METHOD."""
    code = "\n".join([f"    line_{i} = {i}" for i in range(25)])
    kind = classify_replacement_span(code, "old_code")
    assert kind == ReplacementSpanKind.BROAD_METHOD


# ─── Span Acceptability Tests ────────────────────────────────────────────────

def test_small_spans_acceptable():
    """Small spans should be acceptable."""
    for kind in [
        ReplacementSpanKind.SINGLE_RETURN,
        ReplacementSpanKind.SINGLE_ASSIGNMENT,
        ReplacementSpanKind.ONE_IF_BRANCH,
        ReplacementSpanKind.LOCALIZED_BLOCK,
    ]:
        assert is_span_acceptable(kind) is True


def test_broad_method_rejected():
    """Broad method should be rejected."""
    assert is_span_acceptable(ReplacementSpanKind.BROAD_METHOD) is False


def test_strict_leaf_rejects_broad():
    """Strict leaf mode should reject broad methods."""
    assert is_span_acceptable(ReplacementSpanKind.BROAD_METHOD, strict_leaf=True) is False
    assert is_span_acceptable(ReplacementSpanKind.LOCALIZED_BLOCK, strict_leaf=True) is True


# ─── Duplicate Detection Tests ───────────────────────────────────────────────

def test_duplicate_detection():
    """Duplicates should be detected."""
    seen = set()
    assert is_duplicate("return x + 1", seen) is False
    assert is_duplicate("return x + 1", seen) is True
    assert is_duplicate("return x + 2", seen) is False


def test_duplicate_normalizes_whitespace():
    """Duplicates should normalize whitespace."""
    seen = set()
    assert is_duplicate("return x + 1", seen) is False
    assert is_duplicate("  return  x  +  1  ", seen) is True


# ─── Prompt Builder Tests ────────────────────────────────────────────────────

def test_narrow_span_prompt_includes_max_lines():
    """Prompt should include max lines constraint."""
    sys, usr = build_narrow_span_prompt(
        problem="test bug",
        anchor_text="old code",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        variant=0,
        max_replacement_lines=8,
    )
    assert "max 8 lines" in sys
    assert "ABSTAIN" in sys


def test_intent_prompt_no_code():
    """Intent prompt should not ask for code."""
    sys, usr = build_intent_prompt(
        problem="test bug",
        anchor_text="old code",
        symbol="func",
    )
    assert "no code" in sys.lower()
    assert "TARGET:" in sys


def test_retry_feedback_included():
    """Retry feedback should be included in prompt."""
    sys, usr = build_narrow_span_prompt(
        problem="test bug",
        anchor_text="old code",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        variant=0,
        retry_feedback="Parser rejected: prose contamination",
    )
    assert "PREVIOUS REJECTED" in usr
    assert "prose contamination" in usr


# ─── Candidate Metadata Tests ────────────────────────────────────────────────

def test_candidate_has_required_fields():
    """Candidate should have all required metadata fields."""
    candidate = NarrowSpanCandidate(
        candidate_id="test_v1",
        model="test_model",
        prompt_variant=0,
        replacement_span_kind=ReplacementSpanKind.SINGLE_RETURN,
        parser_status=CandidateParserStatus.ACCEPTED,
        patch_status=CandidatePatchStatus.APPLIED,
    )
    assert candidate.candidate_id == "test_v1"
    assert candidate.model == "test_model"
    assert candidate.replacement_span_kind == ReplacementSpanKind.SINGLE_RETURN
    assert candidate.parser_status == CandidateParserStatus.ACCEPTED
    assert candidate.selected is False


def test_generation_result_has_required_fields():
    """Generation result should have all required fields."""
    result = CandidateGenerationResult(
        task_id="test_task",
        model="test_model",
        candidates=[],
        selected=None,
        abstain_count=0,
        parser_reject_count=0,
        patch_apply_count=0,
        verifier_pass_count=0,
        total_candidates=0,
        status="P14_PARSER_REJECTED_ALL",
    )
    assert result.task_id == "test_task"
    assert result.abstain_count == 0
    assert result.status == "P14_PARSER_REJECTED_ALL"


# ─── High-Level API Tests ────────────────────────────────────────────────────

def test_generate_with_abstain():
    """Generator should handle ABSTAIN responses."""
    def mock_generate(sys, usr, variant_id):
        return "ABSTAIN"

    result = generate_narrow_span_candidates(
        task_id="test",
        model_name="mock_model",
        problem="test bug",
        anchor_text="old code",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        generate_fn=mock_generate,
        max_candidates=3,
    )

    assert result.abstain_count == 3
    assert result.status == "P14_MODEL_ABSTAINED_ALL"
    assert result.selected is None


def test_generate_with_prose_rejection():
    """Generator should reject prose responses."""
    call_count = [0]
    def mock_generate(sys, usr, variant_id):
        call_count[0] += 1
        if call_count[0] == 1:
            return "Here is the fix:\ndef func():\n    return 42"
        elif call_count[0] == 2:
            return "The following code replaces:\ndef func():\n    return 42"
        return "ABSTAIN"

    result = generate_narrow_span_candidates(
        task_id="test",
        model_name="mock_model",
        problem="test bug",
        anchor_text="def func():\n    pass",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        generate_fn=mock_generate,
        max_candidates=3,
    )

    # First is prose (rejected), second is prose but different (rejected), third is ABSTAIN
    assert result.parser_reject_count >= 1
    assert result.abstain_count >= 1


def test_generate_with_valid_replacement():
    """Generator should accept valid code replacements."""
    def mock_generate(sys, usr, variant_id):
        return "def func():\n    return 42"

    def mock_verify(replacement):
        return True, "SUCCESS"

    result = generate_narrow_span_candidates(
        task_id="test",
        model_name="mock_model",
        problem="test bug",
        anchor_text="def func():\n    pass",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        generate_fn=mock_generate,
        verify_fn=mock_verify,
        max_candidates=1,
    )

    assert result.patch_apply_count == 1
    assert result.verifier_pass_count == 1
    assert result.selected is not None
    assert result.status == "P14_VERIFIER_PASS_INTERNAL_ONLY"


def test_generate_rejects_markdown():
    """Generator should reject markdown fences."""
    def mock_generate(sys, usr, variant_id):
        return "```python\ndef func():\n    return 42\n```"

    result = generate_narrow_span_candidates(
        task_id="test",
        model_name="mock_model",
        problem="test bug",
        anchor_text="def func():\n    pass",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        generate_fn=mock_generate,
        max_candidates=1,
    )

    assert result.parser_reject_count == 1
    assert result.candidates[0].parser_status == CandidateParserStatus.REJECTED_MARKDOWN


def test_generate_rejects_duplicates():
    """Generator should reject duplicate replacements."""
    call_count = [0]
    def mock_generate(sys, usr, variant_id):
        call_count[0] += 1
        return "def func():\n    return 42"

    result = generate_narrow_span_candidates(
        task_id="test",
        model_name="mock_model",
        problem="test bug",
        anchor_text="def func():\n    pass",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        generate_fn=mock_generate,
        max_candidates=3,
    )

    # First accepted, duplicates rejected
    accepted = sum(1 for c in result.candidates if c.parser_status == CandidateParserStatus.ACCEPTED)
    duplicates = sum(1 for c in result.candidates if c.parser_status == CandidateParserStatus.REJECTED_DUPLICATE)
    assert accepted == 1
    assert duplicates == 2


def test_generate_no_success_without_verifier():
    """Generator should not select without verifier pass."""
    def mock_generate(sys, usr, variant_id):
        return "def func():\n    return 42"

    def mock_verify(replacement):
        return False, "FAIL"

    result = generate_narrow_span_candidates(
        task_id="test",
        model_name="mock_model",
        problem="test bug",
        anchor_text="def func():\n    pass",
        anchor_intent="fix it",
        symbol="func",
        source_context="context",
        generate_fn=mock_generate,
        verify_fn=mock_verify,
        max_candidates=2,
    )

    assert result.selected is None
    assert result.status == "P14_PATCH_APPLIED_VERIFIER_FAILED"
