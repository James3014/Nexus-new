from pathlib import Path

from scripts.bench.route_decision_simulator import (
    build_launch_readiness_gate,
    build_route_cost_preflight_gate,
    simulate_route_decision,
)


def test_simulate_route_decision_allows_low_risk_supervised_bare_first(tmp_path: Path) -> None:
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:low-risk-hidden-lite",
                    "match": {
                        "task_type": "public_bugfix",
                        "local_reflex_risk_level": "low",
                        "local_reflex_bare_sufficiency": "high",
                    },
                    "controls": {
                        "candidate_cap": 1,
                        "lite_route": True,
                        "supervised_bare_first": True,
                    },
                }
            ],
        }
    }

    out = simulate_route_decision(
        tmp_path,
        task_id="fixture-1",
        route_features={
            "task_type": "public_bugfix",
            "local_reflex_risk_level": "low",
            "local_reflex_bare_sufficiency": "high",
        },
        budget=budget,
    )

    assert out["supervised_bare_first_allowed"] is True
    assert out["runtime_classification"] == "nexus_supervised_bare_first_candidate"
    assert out["controls"]["policy_source"] == "feature:low-risk-hidden-lite"


def test_simulate_route_decision_protects_expected_ddtree_from_lite_controls(tmp_path: Path) -> None:
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:low-risk-hidden-lite",
                    "match": {"task_type": "public_bugfix"},
                    "controls": {
                        "candidate_cap": 1,
                        "lite_route": True,
                        "supervised_bare_first": True,
                    },
                }
            ],
        }
    }

    out = simulate_route_decision(
        tmp_path,
        task_id="route-oracle-ddtree-001",
        route_features={"task_type": "public_bugfix"},
        expected_capabilities=["ddtree"],
        budget=budget,
    )

    assert out["expected_capabilities"] == ["ddtree"]
    assert out["controls"]["candidate_cap"] == 3
    assert out["controls"]["lite_route"] is False
    assert out["controls"]["supervised_bare_first"] is False
    assert out["controls"]["expected_capability_protection"] == ["ddtree"]


def test_simulate_route_decision_blocks_medium_without_explicit_override(tmp_path: Path) -> None:
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:medium-no-override",
                    "match": {"task_type": "public_bugfix"},
                    "controls": {"supervised_bare_first": True},
                }
            ],
        }
    }

    out = simulate_route_decision(
        tmp_path,
        task_id="fixture-2",
        route_features={
            "task_type": "public_bugfix",
            "local_reflex_risk_level": "medium",
            "local_reflex_bare_sufficiency": "medium",
        },
        budget=budget,
    )

    assert out["supervised_bare_first_allowed"] is False
    assert out["supervised_bare_first_block_reason"] == "local_reflex_risk_not_admitted"


def test_preflight_gate_fails_supervised_bare_without_hidden_verifier(tmp_path: Path) -> None:
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:low-risk-hidden-lite",
                    "match": {"task_type": "public_bugfix"},
                    "controls": {"supervised_bare_first": True},
                }
            ],
        }
    }

    out = build_route_cost_preflight_gate(
        tmp_path,
        tasks=[
            {
                "task_id": "fixture-3",
                "task_type": "public_bugfix",
                "local_reflex_risk_level": "low",
                "local_reflex_bare_sufficiency": "high",
            }
        ],
        budget=budget,
        hidden_verifier_required=False,
    )

    assert out["passed"] is False
    assert out["failures"][0]["reason"] == "supervised_bare_first_requires_hidden_verifier"


def test_preflight_gate_flags_broad_medium_supervised_policy(tmp_path: Path) -> None:
    budget = {
        "route_cost_policy": {
            "source": "test",
            "feature_rules": [
                {
                    "id": "feature:broad-medium",
                    "match": {"category": "feature"},
                    "controls": {
                        "allow_medium_risk_supervised_bare_first": True,
                        "supervised_bare_first": True,
                    },
                }
            ],
        }
    }

    out = build_route_cost_preflight_gate(
        tmp_path,
        tasks=[
            {
                "task_id": "fixture-4",
                "category": "feature",
                "local_reflex_risk_level": "medium",
                "local_reflex_bare_sufficiency": "medium",
            }
        ],
        budget=budget,
    )

    assert out["passed"] is False
    assert out["failures"][0]["reason"] == "broad_medium_supervised_bare_first"


def test_launch_readiness_gate_accepts_verified_same_model_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        """
{
  "model_lock": {"same_model": true, "with_model_name": "gemini-3-flash-preview"},
  "row_count": 16,
  "row_counts": {"with_nexus": 16, "without_nexus": 16},
  "public_claim_gate": {
    "verdict": "PASS",
    "checks": {
      "with_semantic_verified_rate": 1.0,
      "without_semantic_verified_rate": 0.75,
      "trust_mismatch_free": true,
      "wall_cost_ratio_with_over_without": 1.4,
      "median_paired_wall_cost_ratio_with_over_without": 1.1,
      "token_cost_ratio_with_over_without": 1.2
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    out = build_launch_readiness_gate([bundle])

    assert out["passed"] is True
    assert out["bundles_checked"] == 1
    assert out["warnings"] == []
