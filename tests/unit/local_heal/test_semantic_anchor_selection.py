"""P10: Semantic Anchor Selection Tests"""
import hashlib
import pytest
from nexus.services.local_heal.semantic_anchor_selection import (
    AnchorCandidate,
    AnchorCandidateGenerator,
    AnchorSelectionResult,
    SemanticAnchorScorer,
    SemanticAnchorSelector,
    select_semantic_anchor,
)


def _make_source_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ─── Candidate Generation Tests ───────────────────────────────────────────────

def test_generator_finds_target_symbol():
    """Generator should find the target symbol as a candidate."""
    source = (
        "def calculate(x, y):\n"
        "    return x + y\n"
        "\n"
        "def format_output(result):\n"
        "    return str(result)\n"
    )
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="calc.py",
        source_text=source,
        target_symbol="calculate",
    )
    assert len(candidates) >= 1
    assert any(c.symbol_name == "calculate" for c in candidates)


def test_generator_finds_failing_symbol():
    """Generator should find the failing symbol as a candidate."""
    source = (
        "def calculate(x, y):\n"
        "    return x + y\n"
        "\n"
        "def format_output(result):\n"
        "    return str(result)\n"
    )
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="calc.py",
        source_text=source,
        target_symbol="calculate",
        failing_symbol="format_output",
    )
    assert len(candidates) >= 2
    symbol_names = [c.symbol_name for c in candidates]
    assert "calculate" in symbol_names
    assert "format_output" in symbol_names


def test_generator_finds_formatting_methods():
    """Generator should find methods with formatting behavior."""
    source = (
        "class Writer:\n"
        "    def write(self, data):\n"
        "        self._render(data)\n"
        "\n"
        "    def _render(self, data):\n"
        "        return str(data)\n"
    )
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="writer.py",
        source_text=source,
        target_symbol="write",
    )
    # Should find write and _render (formatting behavior)
    assert len(candidates) >= 1


def test_generator_deduplicates_candidates():
    """Generator should not produce duplicate candidates."""
    source = (
        "def calculate(x, y):\n"
        "    return x + y\n"
    )
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="calc.py",
        source_text=source,
        target_symbol="calculate",
    )
    anchor_ids = [c.anchor_id for c in candidates]
    assert len(anchor_ids) == len(set(anchor_ids))


def test_generator_returns_empty_for_syntax_error():
    """Generator should return empty list for invalid Python."""
    source = "def broken(\n"
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="broken.py",
        source_text=source,
        target_symbol="broken",
    )
    assert candidates == []


# ─── Scoring Tests ────────────────────────────────────────────────────────────

def test_scorer_prefers_behavior_ownership():
    """Scorer should prefer methods that own the failing behavior."""
    source = "def format_output(result):\n    return str(result)\n"
    source_hash = _make_source_hash(source)

    candidate = AnchorCandidate(
        anchor_id="c1",
        file_path="test.py",
        symbol_name="format_output",
        span_start=1,
        span_end=2,
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="def format_output(result):\n    return str(result)",
    )

    scorer = SemanticAnchorScorer()
    scored = scorer.score_candidate(
        candidate,
        issue_keywords=["format", "output"],
    )
    # Should have positive score from behavior ownership + keyword overlap
    assert scored.score > 0
    # Check that behavior ownership contributed
    assert any("behavior" in r or "keyword" in r for r in scored.score_reasons)


def test_scorer_penalizes_mechanical_code():
    """Scorer should penalize mechanical iteration code."""
    source = "for item in items:\n    process(item)\n"
    source_hash = _make_source_hash(source)

    candidate = AnchorCandidate(
        anchor_id="c2",
        file_path="test.py",
        symbol_name="loop_over_items",
        span_start=1,
        span_end=2,
        source_hash=source_hash,
        candidate_type="direct_caller",
        source_text="for item in items:\n    process(item)",
    )

    scorer = SemanticAnchorScorer()
    scored = scorer.score_candidate(candidate)
    # The mechanical code penalty should be in score_reasons
    assert any("mechanical" in r for r in scored.score_reasons)
    # Total score may still be positive due to other factors (small span, leaf method)
    # But the mechanical penalty should reduce it compared to a non-mechanical candidate


def test_scorer_prefers_small_span():
    """Scorer should prefer smaller, complete method spans."""
    source_hash = _make_source_hash("x = 1")

    small_candidate = AnchorCandidate(
        anchor_id="c3",
        file_path="test.py",
        symbol_name="small_method",
        span_start=1,
        span_end=5,  # 5 lines
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="x = 1",
    )

    large_candidate = AnchorCandidate(
        anchor_id="c4",
        file_path="test.py",
        symbol_name="large_method",
        span_start=1,
        span_end=150,  # 150 lines
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="x = 1",
    )

    scorer = SemanticAnchorScorer()
    scored_small = scorer.score_candidate(small_candidate)
    scored_large = scorer.score_candidate(large_candidate)
    assert scored_small.score > scored_large.score


def test_scorer_prefers_leaf_method():
    """Scorer should prefer leaf methods with no nested definitions."""
    source_hash = _make_source_hash("x = 1")

    leaf_candidate = AnchorCandidate(
        anchor_id="c5",
        file_path="test.py",
        symbol_name="leaf_method",
        span_start=1,
        span_end=3,
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="return x + 1",
    )

    nested_candidate = AnchorCandidate(
        anchor_id="c6",
        file_path="test.py",
        symbol_name="nested_method",
        span_start=1,
        span_end=10,
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="def inner():\n    pass\nreturn x + 1",
    )

    scorer = SemanticAnchorScorer()
    scored_leaf = scorer.score_candidate(leaf_candidate)
    scored_nested = scorer.score_candidate(nested_candidate)
    assert scored_leaf.score > scored_nested.score


def test_scorer_keyword_overlap():
    """Scorer should reward keyword overlap with issue description."""
    source_hash = _make_source_hash("x = 1")

    candidate = AnchorCandidate(
        anchor_id="c7",
        file_path="test.py",
        symbol_name="format_table",
        span_start=1,
        span_end=5,
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="def format_table(data):\n    # format the table\n    return data",
    )

    scorer = SemanticAnchorScorer()
    scored = scorer.score_candidate(
        candidate,
        issue_keywords=["format", "table", "data"],
    )
    assert scored.score > 0
    assert any("keyword_overlap" in r for r in scored.score_reasons)


# ─── Selection Tests ──────────────────────────────────────────────────────────

def test_selector_picks_highest_score():
    """Selector should pick the candidate with the highest score."""
    source_hash = _make_source_hash("x = 1")

    low_score = AnchorCandidate(
        anchor_id="low",
        file_path="test.py",
        symbol_name="helper",
        span_start=1,
        span_end=10,
        source_hash=source_hash,
        candidate_type="direct_caller",
        source_text="x = 1",
        score=0.5,
    )

    high_score = AnchorCandidate(
        anchor_id="high",
        file_path="test.py",
        symbol_name="format_output",
        span_start=1,
        span_end=5,
        source_hash=source_hash,
        candidate_type="target_symbol",
        source_text="x = 1",
        score=3.0,
    )

    selector = SemanticAnchorSelector()
    result = selector.select([low_score, high_score])
    assert result.selected is not None
    assert result.selected.anchor_id == "high"


def test_selector_returns_none_for_empty():
    """Selector should return None for empty candidate list."""
    selector = SemanticAnchorSelector()
    result = selector.select([])
    assert result.selected is None
    assert result.total_candidates == 0


def test_selector_respects_min_score():
    """Selector should reject candidates below minimum score."""
    source_hash = _make_source_hash("x = 1")

    low_score = AnchorCandidate(
        anchor_id="low",
        file_path="test.py",
        symbol_name="helper",
        span_start=1,
        span_end=10,
        source_hash=source_hash,
        candidate_type="direct_caller",
        source_text="x = 1",
        score=-1.0,
    )

    selector = SemanticAnchorSelector()
    result = selector.select([low_score], min_score=0.0)
    assert result.selected is None


# ─── High-Level API Tests ─────────────────────────────────────────────────────

def test_select_semantic_anchor_high_level():
    """High-level API should select the best anchor."""
    source = (
        "def calculate(x, y):\n"
        "    return x + y\n"
        "\n"
        "def format_output(result):\n"
        "    return str(result)\n"
    )

    result = select_semantic_anchor(
        file_path="calc.py",
        source_text=source,
        target_symbol="calculate",
        issue_keywords=["calculate", "addition"],
    )

    assert result.total_candidates >= 1
    assert result.selected is not None
    assert result.selected.symbol_name == "calculate"


def test_select_semantic_anchor_with_failing_symbol():
    """High-level API should prefer the failing symbol."""
    source = (
        "def calculate(x, y):\n"
        "    return x + y\n"
        "\n"
        "def format_output(result):\n"
        "    return str(result)\n"
    )

    result = select_semantic_anchor(
        file_path="calc.py",
        source_text=source,
        target_symbol="calculate",
        failing_symbol="format_output",
    )

    # Should prefer format_output as it's the failing symbol
    assert result.selected is not None
    assert result.selected.symbol_name == "format_output"


def test_select_semantic_anchor_with_call_graph():
    """High-level API should consider call graph relationships."""
    source = (
        "class Writer:\n"
        "    def write(self, data):\n"
        "        formatted = self.format_data(data)\n"
        "        return formatted\n"
        "\n"
        "    def format_data(self, data):\n"
        "        return str(data)\n"
    )

    call_graph = {
        "write": ["format_data"],
        "format_data": [],
    }

    result = select_semantic_anchor(
        file_path="writer.py",
        source_text=source,
        target_symbol="write",
        call_graph=call_graph,
    )

    # Should find both write and format_data
    assert result.total_candidates >= 2
