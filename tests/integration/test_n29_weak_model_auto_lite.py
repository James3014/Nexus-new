from nexus.core.lite_route_oracle import should_use_lite_route


def test_unsafe_weak_7b_is_blocked():
    """Unsafe signals (impact_complexity > 3.0, confidence < 0.85) block 7B auto-lite."""
    decision = should_use_lite_route(
        risk_level="NORMAL",
        impact_complexity=4.0,
        belief_confidence=0.5,
        model_size=7_000_000_000,
    )
    assert decision.is_lite is False
    assert decision.reason == "standard_heavy_route_blocked_lite"
    assert decision.skipped_phases == []


def test_unsafe_strong_14b_is_blocked():
    """Unsafe signals block 14B model identically."""
    decision = should_use_lite_route(
        risk_level="NORMAL",
        impact_complexity=4.0,
        belief_confidence=0.5,
        model_size=14_000_000_000,
    )
    assert decision.is_lite is False
    assert decision.reason == "standard_heavy_route_blocked_lite"
    assert decision.skipped_phases == []


def test_safe_weak_7b_recommends_lite():
    """Safe 7B task (low complexity, confidence=1.0) recommends weak model auto-lite."""
    decision = should_use_lite_route(
        risk_level="NORMAL",
        impact_complexity=2.0,
        belief_confidence=1.0,
        model_size=7_000_000_000,
        cross_module=False,
        hard_signal=False,
        candidate_count=1,
    )
    assert decision.is_lite is True
    assert decision.reason == "auto_lite_weak_model_size_lt_8B"
    assert "X" in decision.skipped_phases
    assert "D" in decision.skipped_phases
    assert "A" in decision.skipped_phases


def test_safe_strong_14b_remains_heavy():
    """Safe 14B task with confidence=1.0 remains standard heavy route."""
    decision = should_use_lite_route(
        risk_level="NORMAL",
        impact_complexity=2.0,
        belief_confidence=1.0,
        model_size=14_000_000_000,
        cross_module=False,
        hard_signal=False,
        candidate_count=1,
    )
    assert decision.is_lite is False
    assert decision.reason == "standard_heavy_route"


def test_safe_low_risk_uses_lite_regardless_of_model_size():
    """Safe LOW-risk task (low complexity, high confidence) uses auto-lite regardless of model size."""
    decision = should_use_lite_route(
        risk_level="LOW",
        impact_complexity=2.0,
        belief_confidence=0.90,
        model_size=14_000_000_000,
    )
    assert decision.is_lite is True
    assert decision.reason == "auto_lite_low_risk_low_complexity"


def test_low_risk_low_confidence_remains_blocked():
    """LOW-risk task with low confidence (< 0.85) remains blocked from lite mode."""
    decision = should_use_lite_route(
        risk_level="LOW",
        impact_complexity=2.0,
        belief_confidence=0.5,
        model_size=7_000_000_000,
    )
    assert decision.is_lite is False
    assert decision.reason == "standard_heavy_route_blocked_lite"
