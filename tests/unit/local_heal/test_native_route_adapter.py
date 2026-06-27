from nexus.services.local_heal.native_route_adapter import (
    EXPLICIT_ROUTE_PROFILE,
    NativeRouteAdapter,
    RouteRequest,
)


def test_explicit_manual_route_is_allowed_only_with_local_patterns():
    adapter = NativeRouteAdapter()
    request = RouteRequest(
        task_id="u3-manual-route",
        repo_path="/Users/jameschen/Workspace/nexus",
        base_commit="base",
        issue_summary="repair local_h heal path with traceback",
        failing_test_summary="AssertionError in tests/unit/local_heal/test_role_contract.py",
        selected_anchor="def build_role_receipt(...):",
        model_role_requested="judge",
        resource_profile="local",
        phase="judge",
        route_profile=EXPLICIT_ROUTE_PROFILE,
        route_metadata={
            "manual_only_experimental": True,
            "manual_invocation_only": True,
            "route_profile": EXPLICIT_ROUTE_PROFILE,
        },
    )

    decision = adapter.decide(request)

    assert decision.explicit_route is True
    assert decision.route_allowed is True
    assert decision.route_metadata["has_local_patterns"] is True
    assert decision.route_profile == EXPLICIT_ROUTE_PROFILE
    assert decision.allowed_capabilities == ["evidence_ranking", "gate_review"]
    assert decision.forbidden_capabilities == ["patch_generation"]
    assert decision.route_metadata["manual_invocation_only"] is True


def test_explicit_route_stays_blocked_without_opt_in_metadata():
    adapter = NativeRouteAdapter()
    request = RouteRequest(
        task_id="u3-auto-route",
        repo_path="/Users/jameschen/Workspace/nexus",
        base_commit="base",
        issue_summary="traceback in local_heal test",
        failing_test_summary="AssertionError in tests/unit/local_heal/test_role_contract.py",
        selected_anchor="def build_role_receipt(...):",
        model_role_requested="judge",
        resource_profile="local",
        phase="judge",
        route_profile=EXPLICIT_ROUTE_PROFILE,
    )

    decision = adapter.decide(request)

    assert decision.explicit_route is False
    assert decision.route_allowed is False
    assert "route_not_explicitly_opted_in" in decision.forbidden_capabilities
    assert "manual_only_experimental_missing" in decision.gate_reasons


def test_empty_profile_preserves_legacy_route_rules():
    adapter = NativeRouteAdapter()
    request = RouteRequest(
        task_id="legacy-route",
        repo_path="/Users/jameschen/Workspace/nexus",
        base_commit="base",
        issue_summary="traceback in local_heal test",
        failing_test_summary="AssertionError in tests/unit/local_heal/test_role_contract.py",
        selected_anchor="def build_role_receipt(...):",
        model_role_requested="7b",
        resource_profile="local",
        phase="candidate_generation",
    )

    decision = adapter.decide(request)

    assert decision.explicit_route is False
    assert decision.route_allowed is True
    assert decision.allowed_capabilities == ["narrow_candidate_generation", "abstain"]
