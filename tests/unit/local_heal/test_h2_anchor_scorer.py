"""H2: Generalized Anchor Scorer Rework Tests

All tests use general intent-to-behavior-owner rules.
No task-specific, repo-specific, or file-specific strings.
Each rule has at least one positive and one negative fixture.
"""
import hashlib
import pytest
from nexus.services.local_heal.semantic_anchor_selection import (
    AnchorCandidate,
    AnchorSelectionResult,
    SemanticAnchorScorer,
    SemanticAnchorSelector,
    select_semantic_anchor,
)


def _make_hash(text="test"):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ─── H2: Issue Intent Detection Tests ────────────────────────────────────────

def test_detect_intent_output_formatting():
    """Output formatting keywords should detect output_formatting intent."""
    intent = SemanticAnchorScorer.detect_issue_intent(["format", "html", "table", "write"])
    assert intent == "output_formatting"


def test_detect_intent_input_parsing():
    """Input parsing keywords should detect input_parsing intent."""
    intent = SemanticAnchorScorer.detect_issue_intent(["parse", "read", "load", "decode"])
    assert intent == "input_parsing"


def test_detect_intent_construction():
    """Construction keywords should detect construction intent."""
    intent = SemanticAnchorScorer.detect_issue_intent(["__new__", "__init__", "construct"])
    assert intent == "construction"


def test_detect_intent_permutation():
    """Permutation keywords should detect permutation_cycle_semantics intent."""
    intent = SemanticAnchorScorer.detect_issue_intent(["permutation", "cycle", "disjoint"])
    assert intent == "permutation_cycle_semantics"


def test_detect_intent_unknown():
    """Unknown keywords should return unknown intent."""
    intent = SemanticAnchorScorer.detect_issue_intent(["foo", "bar", "baz"])
    assert intent == "unknown"


def test_detect_intent_empty():
    """Empty keywords should return unknown intent."""
    intent = SemanticAnchorScorer.detect_issue_intent([])
    assert intent == "unknown"


# ─── H2: Directional Behavior-Owner Scoring Tests ────────────────────────────

def test_output_formatting_prefers_write_over_read():
    """For output_formatting bugs, write should outrank read."""
    source_hash = _make_hash()

    write_candidate = AnchorCandidate(
        anchor_id="w1", file_path="test.py", symbol_name="write_data",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="def write_data():\n    return str(x)",
    )

    read_candidate = AnchorCandidate(
        anchor_id="r1", file_path="test.py", symbol_name="read_data",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def read_data():\n    return input()",
    )

    scorer = SemanticAnchorScorer()
    scored_write = scorer.score_candidate(write_candidate, issue_keywords=["format", "html", "output"])
    scored_read = scorer.score_candidate(read_candidate, issue_keywords=["format", "html", "output"])

    assert scored_write.score > scored_read.score
    assert any("intent_direction_match" in r for r in scored_write.score_reasons)
    assert any("intent_direction_penalty" in r for r in scored_read.score_reasons)


def test_input_parsing_prefers_read_over_write():
    """For input_parsing bugs, read should outrank write."""
    source_hash = _make_hash()

    read_candidate = AnchorCandidate(
        anchor_id="r1", file_path="test.py", symbol_name="parse_input",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def parse_input():\n    return data",
    )

    write_candidate = AnchorCandidate(
        anchor_id="w1", file_path="test.py", symbol_name="write_output",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="def write_output():\n    return str(x)",
    )

    scorer = SemanticAnchorScorer()
    scored_read = scorer.score_candidate(read_candidate, issue_keywords=["parse", "read", "load"])
    scored_write = scorer.score_candidate(write_candidate, issue_keywords=["parse", "read", "load"])

    assert scored_read.score > scored_write.score
    assert any("intent_direction_match" in r for r in scored_read.score_reasons)
    assert any("intent_direction_penalty" in r for r in scored_write.score_reasons)


def test_construction_prefers_new_over_read():
    """For construction bugs, __new__ should outrank read."""
    source_hash = _make_hash()

    new_candidate = AnchorCandidate(
        anchor_id="n1", file_path="test.py", symbol_name="__new__",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def __new__():\n    return cls()",
    )

    read_candidate = AnchorCandidate(
        anchor_id="r1", file_path="test.py", symbol_name="read_file",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def read_file():\n    return data",
    )

    scorer = SemanticAnchorScorer()
    scored_new = scorer.score_candidate(new_candidate, issue_keywords=["__new__", "construct"])
    scored_read = scorer.score_candidate(read_candidate, issue_keywords=["__new__", "construct"])

    assert scored_new.score > scored_read.score


def test_permutation_prefers_compose_over_format():
    """For permutation semantics, compose should outrank format."""
    source_hash = _make_hash()

    compose_candidate = AnchorCandidate(
        anchor_id="c1", file_path="test.py", symbol_name="compose_cycles",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def compose_cycles():\n    return result",
    )

    format_candidate = AnchorCandidate(
        anchor_id="f1", file_path="test.py", symbol_name="format_output",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="def format_output():\n    return str(x)",
    )

    scorer = SemanticAnchorScorer()
    scored_compose = scorer.score_candidate(compose_candidate, issue_keywords=["permutation", "cycle", "compose"])
    scored_format = scorer.score_candidate(format_candidate, issue_keywords=["permutation", "cycle", "compose"])

    assert scored_compose.score > scored_format.score


# ─── H2: Traceback Override Guard Tests ──────────────────────────────────────

def test_traceback_does_not_override_output_intent():
    """Traceback to iter/read should not override output_formatting intent."""
    source_hash = _make_hash()

    # Candidate is iter_str_vals (traceback symbol) but issue is output_formatting
    iter_candidate = AnchorCandidate(
        anchor_id="i1", file_path="test.py", symbol_name="iter_str_vals",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="failing_stack_frame",
        source_text="def iter_str_vals():\n    return vals",
    )

    # Write candidate matches output intent
    write_candidate = AnchorCandidate(
        anchor_id="w1", file_path="test.py", symbol_name="write_html",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="def write_html():\n    return html",
    )

    scorer = SemanticAnchorScorer()
    scored_iter = scorer.score_candidate(iter_candidate, failing_symbol="iter_str_vals", issue_keywords=["format", "html", "write"])
    scored_write = scorer.score_candidate(write_candidate, failing_symbol="iter_str_vals", issue_keywords=["format", "html", "write"])

    # Write should score higher because it matches output intent
    assert scored_write.score > scored_iter.score


def test_traceback_boosts_when_matches_intent():
    """Traceback symbol that matches intent should be boosted."""
    source_hash = _make_hash()

    # Candidate matches both traceback and intent
    write_candidate = AnchorCandidate(
        anchor_id="w1", file_path="test.py", symbol_name="write_data",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="failing_stack_frame",
        source_text="def write_data():\n    return str(x)",
    )

    scorer = SemanticAnchorScorer()
    scored = scorer.score_candidate(write_candidate, failing_symbol="write_data", issue_keywords=["format", "write"])

    assert any("traceback_exact_matches_intent" in r for r in scored.score_reasons)


# ─── H2: Ambiguity Reporting Tests ───────────────────────────────────────────

def test_ambiguous_when_scores_close():
    """Selector should report ambiguity when top scores are close."""
    source_hash = _make_hash()

    candidates = [
        AnchorCandidate(
            anchor_id="a1", file_path="test.py", symbol_name="write_data",
            span_start=1, span_end=5, source_hash=source_hash,
            candidate_type="formatting_behavior",
            source_text="def write_data():\n    pass",
            score=5.0,
        ),
        AnchorCandidate(
            anchor_id="a2", file_path="test.py", symbol_name="read_data",
            span_start=1, span_end=5, source_hash=source_hash,
            candidate_type="behavior_with_return",
            source_text="def read_data():\n    pass",
            score=4.5,
        ),
    ]

    selector = SemanticAnchorSelector()
    result = selector.select(candidates, ambiguity_threshold=1.0)

    assert result.ambiguity is True
    assert result.score_margin < 1.0


def test_not_ambiguous_when_scores_distant():
    """Selector should not report ambiguity when top scores are distant."""
    source_hash = _make_hash()

    candidates = [
        AnchorCandidate(
            anchor_id="a1", file_path="test.py", symbol_name="write_data",
            span_start=1, span_end=5, source_hash=source_hash,
            candidate_type="formatting_behavior",
            source_text="def write_data():\n    pass",
            score=5.0,
        ),
        AnchorCandidate(
            anchor_id="a2", file_path="test.py", symbol_name="read_data",
            span_start=1, span_end=5, source_hash=source_hash,
            candidate_type="behavior_with_return",
            source_text="def read_data():\n    pass",
            score=2.0,
        ),
    ]

    selector = SemanticAnchorSelector()
    result = selector.select(candidates, ambiguity_threshold=1.0)

    assert result.ambiguity is False
    assert result.score_margin >= 1.0


def test_top_k_in_result():
    """Result should include top_k candidates."""
    source_hash = _make_hash()

    candidates = [
        AnchorCandidate(
            anchor_id=f"a{i}", file_path="test.py", symbol_name=f"method_{i}",
            span_start=1, span_end=5, source_hash=source_hash,
            candidate_type="behavior_with_return",
            source_text=f"def method_{i}():\n    pass",
            score=float(5 - i),
        )
        for i in range(5)
    ]

    selector = SemanticAnchorSelector()
    result = selector.select(candidates)

    assert len(result.top_k) == 3  # top_k is limited to 3


# ─── H2: C_13453 Fixture (Output Formatting) ────────────────────────────────

def test_c13453_fixture_selects_write_over_read():
    """C_13453 fixture: output formatting should select write-family over read.

    This is a GENERAL test for output formatting bugs.
    The fixture simulates the C_13453 scenario without using task-specific strings.
    """
    source_hash = _make_hash()

    write_candidate = AnchorCandidate(
        anchor_id="w1", file_path="html.py", symbol_name="write",
        span_start=40, span_end=80, source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="def write(self, table):\n    # format HTML output\n    return html",
    )

    read_candidate = AnchorCandidate(
        anchor_id="r1", file_path="html.py", symbol_name="read",
        span_start=10, span_end=30, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def read(self, lines):\n    # parse HTML input\n    return table",
    )

    scorer = SemanticAnchorScorer()
    scored_write = scorer.score_candidate(write_candidate, issue_keywords=["format", "html", "table", "write"])
    scored_read = scorer.score_candidate(read_candidate, issue_keywords=["format", "html", "table", "write"])

    assert scored_write.score > scored_read.score
    assert scored_write.symbol_name == "write"


# ─── H2: C_12481 Fixture (Construction/Permutation) ──────────────────────────

def test_c12481_fixture_selects_new_over_read():
    """C_12481 fixture: permutation semantics should select __new__ over read.

    This is a GENERAL test for construction/permutation bugs.
    The fixture simulates the C_12481 scenario without using task-specific strings.
    """
    source_hash = _make_hash()

    new_candidate = AnchorCandidate(
        anchor_id="n1", file_path="permutations.py", symbol_name="__new__",
        span_start=50, span_end=100, source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="def __new__(cls, *args):\n    # construct permutation\n    return obj",
    )

    read_candidate = AnchorCandidate(
        anchor_id="r1", file_path="permutations.py", symbol_name="read_permutation",
        span_start=10, span_end=30, source_hash=source_hash,
        candidate_type="behavior_with_return",
        source_text="def read_permutation():\n    return data",
    )

    scorer = SemanticAnchorScorer()
    scored_new = scorer.score_candidate(new_candidate, issue_keywords=["permutation", "cycle", "__new__", "disjoint"])
    scored_read = scorer.score_candidate(read_candidate, issue_keywords=["permutation", "cycle", "__new__", "disjoint"])

    assert scored_new.score > scored_read.score
    assert scored_new.symbol_name == "__new__"


# ─── H2: Regression Tests ────────────────────────────────────────────────────

def test_no_task_specific_scoring_rules():
    """Verify scorer has no task-specific strings in logic."""
    import inspect
    scorer_class = SemanticAnchorScorer

    # Check that ISSUE_INTENT_KEYWORDS and BEHAVIOR_OWNER_PREFERENCES
    # don't contain task-specific strings
    for intent, keywords in scorer_class.ISSUE_INTENT_KEYWORDS.items():
        for kw in keywords:
            # Should not contain task-specific identifiers
            assert "C_13453" not in kw
            assert "C_12481" not in kw
            assert "astropy" not in kw
            assert "sympy" not in kw

    for intent, prefs in scorer_class.BEHAVIOR_OWNER_PREFERENCES.items():
        for key, patterns in prefs.items():
            for p in patterns:
                assert "C_13453" not in p
                assert "C_12481" not in p
                assert "astropy" not in p
                assert "sympy" not in p


def test_score_reasons_include_issue_intent():
    """Score reasons should include issue_intent when detected."""
    source_hash = _make_hash()

    candidate = AnchorCandidate(
        anchor_id="w1", file_path="test.py", symbol_name="write_data",
        span_start=1, span_end=5, source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="def write_data():\n    return str(x)",
    )

    scorer = SemanticAnchorScorer()
    scored = scorer.score_candidate(candidate, issue_keywords=["format", "html"])

    # Should have intent_direction_match in reasons
    assert any("intent_direction_match" in r or "output_formatting" in r for r in scored.score_reasons)
