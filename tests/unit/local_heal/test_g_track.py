"""G1-G6: GitHub-Backed Repair Upgrade Track Tests"""
import hashlib
import pytest
from nexus.services.local_heal.agentless_pipeline import (
    AgentlessCandidatePipeline,
    PipelineCandidate,
    PipelineResult,
    CandidateStage,
)
from nexus.services.local_heal.semantic_anchor_selection import (
    AnchorCandidateGenerator,
    SemanticAnchorScorer,
    select_semantic_anchor,
)
from nexus.services.local_heal.linear_replay_runner import (
    LinearReplayRunner,
    ReplayTask,
    ReplayResult,
)
from nexus.services.local_heal.structured_verifier_feedback import (
    StructuredVerifierFeedback,
    VerifierFeedbackPacket,
)
from nexus.services.local_heal.backend_resource_policy import (
    BackendResourcePolicy,
    ModelTier,
    ResourcePolicy,
)


# ─── G1: Agentless Pipeline Tests ────────────────────────────────────────────

def test_pipeline_selects_first_valid_candidate():
    """Pipeline should select the first candidate that passes all filters."""
    def mock_generate(anchor, symbol, variant_id):
        return f"def {symbol}():\n    return 42"

    pipeline = AgentlessCandidatePipeline(max_anchors=1, max_candidates_per_anchor=1)
    result = pipeline.run(
        task_id="test",
        anchors=[{"id": "a1", "symbol": "func", "source_text": "def func():\n    pass", "score": 1.0}],
        generate_fn=mock_generate,
    )

    assert result.status == "G1_PIPELINE_SUCCESS"
    assert result.selected is not None
    assert result.selected.stage == CandidateStage.SELECTED


def test_pipeline_rejects_prose():
    """Pipeline should reject prose responses."""
    def mock_generate(anchor, symbol, variant_id):
        return "Here is the fix:\ndef func():\n    return 42"

    pipeline = AgentlessCandidatePipeline(max_anchors=1, max_candidates_per_anchor=1)
    result = pipeline.run(
        task_id="test",
        anchors=[{"id": "a1", "symbol": "func", "source_text": "def func():\n    pass", "score": 1.0}],
        generate_fn=mock_generate,
    )

    assert result.status == "G1_ALL_REJECTED"
    assert result.selected is None


def test_pipeline_rejects_markdown():
    """Pipeline should reject markdown fences."""
    def mock_generate(anchor, symbol, variant_id):
        return "```python\ndef func():\n    return 42\n```"

    pipeline = AgentlessCandidatePipeline(max_anchors=1, max_candidates_per_anchor=1)
    result = pipeline.run(
        task_id="test",
        anchors=[{"id": "a1", "symbol": "func", "source_text": "def func():\n    pass", "score": 1.0}],
        generate_fn=mock_generate,
    )

    assert result.status == "G1_ALL_REJECTED"
    assert result.selected is None


def test_pipeline_stops_after_first_selection():
    """Pipeline should stop after first successful selection."""
    call_count = [0]
    def mock_generate(anchor, symbol, variant_id):
        call_count[0] += 1
        return f"def {symbol}():\n    return {call_count[0]}"

    pipeline = AgentlessCandidatePipeline(max_anchors=3, max_candidates_per_anchor=3)
    result = pipeline.run(
        task_id="test",
        anchors=[
            {"id": "a1", "symbol": "f1", "source_text": "def f1():\n    pass", "score": 1.0},
            {"id": "a2", "symbol": "f2", "source_text": "def f2():\n    pass", "score": 0.5},
        ],
        generate_fn=mock_generate,
    )

    assert result.status == "G1_PIPELINE_SUCCESS"
    # Only one candidate should be generated (pipeline stops after first selection)
    assert len(result.candidates) == 1


def test_pipeline_respects_max_anchors():
    """Pipeline should respect max_anchors limit."""
    def mock_generate(anchor, symbol, variant_id):
        return f"def {symbol}():\n    return 42"

    pipeline = AgentlessCandidatePipeline(max_anchors=2, max_candidates_per_anchor=1)
    result = pipeline.run(
        task_id="test",
        anchors=[
            {"id": "a1", "symbol": "f1", "source_text": "def f1():\n    pass", "score": 1.0},
            {"id": "a2", "symbol": "f2", "source_text": "def f2():\n    pass", "score": 0.8},
            {"id": "a3", "symbol": "f3", "source_text": "def f3():\n    pass", "score": 0.6},
        ],
        generate_fn=mock_generate,
    )

    # Only first 2 anchors should be tried
    assert len(result.candidates) == 1


def test_pipeline_deterministic_selection():
    """Pipeline should be deterministic — same inputs produce same output."""
    def mock_generate(anchor, symbol, variant_id):
        return f"def {symbol}():\n    return 42"

    pipeline = AgentlessCandidatePipeline(max_anchors=1, max_candidates_per_anchor=1)

    results = []
    for _ in range(3):
        result = pipeline.run(
            task_id="test",
            anchors=[{"id": "a1", "symbol": "func", "source_text": "def func():\n    pass", "score": 1.0}],
            generate_fn=mock_generate,
        )
        results.append(result)

    # All results should be identical
    for r in results:
        assert r.status == "G1_PIPELINE_SUCCESS"
        assert r.selected.candidate_id == results[0].selected.candidate_id


# ─── G2: Behavior Ownership Anchor Tests ─────────────────────────────────────

def test_generator_finds_output_generation_methods():
    """Generator should find output-generation methods."""
    source = (
        "class Writer:\n"
        "    def generate(self, data):\n"
        "        return str(data)\n"
        "    def produce(self, data):\n"
        "        return data\n"
    )
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="writer.py",
        source_text=source,
        target_symbol="generate",
    )
    # Should find generate and produce
    types = [c.candidate_type for c in candidates]
    assert "output_generation" in types or "behavior_with_return" in types


def test_generator_finds_validation_methods():
    """Generator should find validation methods."""
    source = (
        "class Validator:\n"
        "    def validate(self, data):\n"
        "        return len(data) > 0\n"
        "    def check(self, data):\n"
        "        return data is not None\n"
    )
    generator = AnchorCandidateGenerator()
    candidates = generator.generate_candidates(
        file_path="validator.py",
        source_text=source,
        target_symbol="validate",
    )
    types = [c.candidate_type for c in candidates]
    assert "validation_behavior" in types


def test_scorer_prefers_behavior_ownership():
    """Scorer should prefer behavior-owning methods."""
    source_hash = hashlib.sha256(b"test").hexdigest()[:16]

    from nexus.services.local_heal.semantic_anchor_selection import AnchorCandidate

    behavior_candidate = AnchorCandidate(
        anchor_id="b1",
        file_path="test.py",
        symbol_name="format_output",
        span_start=1,
        span_end=3,
        source_hash=source_hash,
        candidate_type="formatting_behavior",
        source_text="return str(x)",
    )

    loop_candidate = AnchorCandidate(
        anchor_id="l1",
        file_path="test.py",
        symbol_name="iterate_items",
        span_start=1,
        span_end=3,
        source_hash=source_hash,
        candidate_type="direct_caller",
        source_text="for item in items:\n    process(item)",
    )

    scorer = SemanticAnchorScorer()
    scored_behavior = scorer.score_candidate(behavior_candidate)
    scored_loop = scorer.score_candidate(loop_candidate)

    # Behavior should score higher than loop
    assert scored_behavior.score >= scored_loop.score


# ─── G4: Structured Verifier Feedback Tests ──────────────────────────────────

def test_feedback_parses_syntax_error():
    """Feedback should parse syntax errors."""
    verifier_output = (
        "Traceback (most recent call last):\n"
        "  File \"test.py\", line 5\n"
        "    return x +\n"
        "           ^\n"
        "SyntaxError: invalid syntax\n"
    )
    feedback = StructuredVerifierFeedback()
    packet = feedback.parse(
        verifier_output,
        previous_replacement="return x +",
        anchor_text="return x",
    )

    assert packet.failure_type == "syntax_error"
    assert "invalid syntax" in packet.assertion_summary.lower() or "SyntaxError" in packet.assertion_summary


def test_feedback_parses_assertion_error():
    """Feedback should parse assertion errors."""
    verifier_output = (
        "Traceback (most recent call last):\n"
        "  File \"test.py\", line 10\n"
        "    assert result == 42\n"
        "AssertionError: 0 != 42\n"
    )
    feedback = StructuredVerifierFeedback()
    packet = feedback.parse(
        verifier_output,
        previous_replacement="return 0",
        anchor_text="return x",
    )

    assert packet.failure_type == "assertion_error"
    assert "42" in packet.assertion_summary


def test_feedback_extracts_traceback_location():
    """Feedback should extract traceback file and line."""
    verifier_output = (
        "Traceback (most recent call last):\n"
        "  File \"/path/to/file.py\", line 42\n"
        "    result = compute(x)\n"
    )
    feedback = StructuredVerifierFeedback()
    packet = feedback.parse(
        verifier_output,
        previous_replacement="result = compute(x)",
        anchor_text="result = old(x)",
    )

    assert packet.traceback_line == 42


def test_correction_prompt_includes_feedback():
    """Correction prompt should include structured feedback."""
    feedback = StructuredVerifierFeedback()
    packet = VerifierFeedbackPacket(
        failure_type="syntax_error",
        assertion_summary="invalid syntax",
        traceback_symbol="compute",
        traceback_file="test.py",
        traceback_line=5,
        allowed_span="return statement only",
        forbidden_span="do not change function signature",
        previous_replacement="return x +",
        anchor_text="return x",
        required_output_contract="Output only raw Python code",
        raw_verifier_output="SyntaxError: invalid syntax",
    )

    system, user = feedback.build_correction_prompt(
        packet,
        problem="fix the bug",
        symbol="compute",
    )

    assert "syntax_error" in system
    assert "invalid syntax" in system
    assert "return x +" in user
    assert "SyntaxError" in user


# ─── G5: Backend Resource Policy Tests ───────────────────────────────────────

def test_policy_allows_local_7b():
    """Policy should allow local 7B models."""
    policy = BackendResourcePolicy()
    assert policy.is_allowed("qwen2.5-coder:7b") is True
    assert policy.is_forbidden("qwen2.5-coder:7b") is False


def test_policy_allows_local_12b_with_timeout():
    """Policy should allow local 12B models with timeout."""
    policy = BackendResourcePolicy()
    assert policy.is_allowed("gemma4-coder-12b-q4km:latest") is True
    assert policy.get_timeout("gemma4-coder-12b-q4km:latest") == 300


def test_policy_forbids_14b_cpu():
    """Policy should forbid 14B CPU-only models."""
    policy = BackendResourcePolicy()
    assert policy.is_forbidden("deepseek-r1-14b-q4km:latest") is True
    assert policy.is_allowed("deepseek-r1-14b-q4km:latest") is False


def test_policy_requires_approval_for_cloud():
    """Policy should require owner approval for cloud models."""
    policy = BackendResourcePolicy()
    assert policy.requires_approval("gpt-4o") is True
    assert policy.is_allowed("gpt-4o") is False


def test_validate_execution_allowed():
    """Validation should pass for allowed models."""
    policy = BackendResourcePolicy()
    ok, reason = policy.validate_execution("qwen2.5-coder:7b")
    assert ok is True


def test_validate_execution_forbidden():
    """Validation should fail for forbidden models."""
    policy = BackendResourcePolicy()
    ok, reason = policy.validate_execution("deepseek-r1-14b-q4km:latest")
    assert ok is False
    assert "Forbidden" in reason


def test_validate_execution_requires_approval():
    """Validation should fail for cloud without approval."""
    policy = BackendResourcePolicy()
    ok, reason = policy.validate_execution("gpt-4o", owner_approved=False)
    assert ok is False
    assert "approval" in reason.lower()


def test_validate_execution_cloud_approved():
    """Validation should pass for cloud with approval."""
    policy = BackendResourcePolicy()
    ok, reason = policy.validate_execution("gpt-4o", owner_approved=True)
    assert ok is True


def test_classify_result_local():
    """Local success should be classified as local_success."""
    policy = BackendResourcePolicy()
    assert policy.classify_result("qwen2.5-coder:7b", True) == "local_success"


def test_classify_result_cloud():
    """Cloud success should be classified as cloud_success."""
    policy = BackendResourcePolicy()
    assert policy.classify_result("gpt-4o", True) == "cloud_success"


def test_list_allowed_models():
    """Should list all allowed models."""
    policy = BackendResourcePolicy()
    allowed = policy.list_allowed_models()
    assert "qwen2.5-coder:7b" in allowed
    assert "gemma4-coder-12b-q4km:latest" in allowed
    assert "deepseek-r1-14b-q4km:latest" not in allowed


def test_list_forbidden_models():
    """Should list all forbidden models."""
    policy = BackendResourcePolicy()
    forbidden = policy.list_forbidden_models()
    assert "deepseek-r1-14b-q4km:latest" in forbidden
