# tests/services/test_swarm_router.py

from nexus.services.swarm_router import RouteCandidate, select_best_route


def test_select_best_route_prefers_healthier_candidate():
    """驗證高成功率 / 低 phantom / 高 pattern reuse 會被優先選中"""
    candidates = [
        RouteCandidate(
            route_id="rust-v16",
            provider="rust",
            armor_id="rust-v16",
            phase="R",
            base_weight=0.7,
            success_rate=0.92,
            pattern_reuse=0.81,
            next_run_hit=0.77,
            phantom_fp_rate=0.03,
            regression_pass_rate=0.96,
        ),
        RouteCandidate(
            route_id="python-v17",
            provider="python",
            armor_id="python-v17",
            phase="R",
            base_weight=0.7,
            success_rate=0.83,
            pattern_reuse=0.62,
            next_run_hit=0.58,
            phantom_fp_rate=0.08,
            regression_pass_rate=0.91,
        ),
    ]

    decision = select_best_route(candidates)
    assert decision.backend_used == "swarm"
    assert decision.selected_route == "rust-v16"
    assert decision.score > 0
    print("\n✅ Swarm Router Preference Verified")


def test_select_best_route_falls_back_when_empty():
    """驗證無候選時 fail-closed，不偽造 legacy route"""
    decision = select_best_route([])
    assert decision.backend_used == "fail-closed"
    assert decision.selected_route == "no-route-available"
    print("✅ Swarm Router Empty Fallback Verified")


def test_select_best_route_falls_back_when_all_unavailable():
    """驗證全不可用時 fail-closed，不偽造 legacy route"""
    candidates = [
        RouteCandidate(
            route_id="route-a",
            provider="x",
            armor_id="a",
            phase="R",
            available=False,
        ),
        RouteCandidate(
            route_id="route-b",
            provider="y",
            armor_id="b",
            phase="R",
            available=False,
        ),
    ]

    decision = select_best_route(candidates)
    assert decision.backend_used == "fail-closed"
    assert decision.selected_route == "no-route-available"
    print("✅ Swarm Router Unavailable Fallback Verified")
