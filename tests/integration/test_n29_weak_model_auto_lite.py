from nexus.core.lite_route_oracle import should_use_lite_route


def test_weak_model_7b_auto_lite():
    """RED: 7B 模型應自動觸發 Lite (跳過 X/D/A)"""
    decision = should_use_lite_route(
        risk_level="NORMAL",
        impact_complexity=4.0,
        belief_confidence=0.5,
        model_size=7_000_000_000,
    )
    assert decision.is_lite is True
    assert decision.reason == "auto_lite_weak_model_size_lt_8B"
    assert "X" in decision.skipped_phases
    assert "D" in decision.skipped_phases
    assert "A" in decision.skipped_phases


def test_strong_model_14b_keeps_heavy_route():
    """RED: 14B 模型應走 7 階段"""
    decision = should_use_lite_route(
        risk_level="NORMAL",
        impact_complexity=4.0,
        belief_confidence=0.5,
        model_size=14_000_000_000,
    )
    assert decision.is_lite is False
    assert decision.reason == "standard_heavy_route"


def test_7b_with_low_risk_still_lite():
    """RED: 7B + LOW risk 應 Lite (原本 auto_lite_low_risk_low_complexity 仍有效)"""
    decision = should_use_lite_route(
        risk_level="LOW",
        impact_complexity=2.0,
        belief_confidence=0.5,
        model_size=7_000_000_000,
    )
    assert decision.is_lite is True


def test_14b_with_low_risk_still_lite():
    """RED: 14B + LOW risk 也應 Lite (與 model_size 無關)"""
    decision = should_use_lite_route(
        risk_level="LOW",
        impact_complexity=2.0,
        belief_confidence=0.5,
        model_size=14_000_000_000,
    )
    assert decision.is_lite is True
    assert "auto_lite_weak_model_size" not in decision.reason
