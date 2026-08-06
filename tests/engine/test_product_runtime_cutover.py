"""Mechanical cutover gates for the daily ``nexus run`` product entry."""

from __future__ import annotations

import ast
import inspect

from nexus.engine import canonical_task_seam
from scripts.engine import nexus_cli


def _assigned_dict_keys(source: str, variable_name: str) -> set[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == variable_name for target in node.targets):
            continue
        if isinstance(node.value, ast.Dict):
            return {
                str(key.value)
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise AssertionError(f"dict assignment not found: {variable_name}")


def test_daily_cli_has_one_production_ingress_and_no_parallel_parent() -> None:
    source = inspect.getsource(nexus_cli.run.callback)

    assert source.count("execute_canonical_product_task(") == 1
    assert "execute_single_task_via_service(" not in source
    assert "CampaignGeneral" not in source
    assert "campaign_master_loop" not in source


def test_product_adapter_has_one_planner_and_one_runtime_entry() -> None:
    source = inspect.getsource(canonical_task_seam.execute_canonical_product_task)

    assert source.count("plan_canonical_task_bundle(") == 1
    assert source.count("gateway.ask_unified(") == 1
    assert "build_command_service(" not in source
    assert "execute_single_task_via_service(" not in source


def test_product_route_has_no_caller_lane_or_target_semantics() -> None:
    source = inspect.getsource(canonical_task_seam.execute_canonical_product_task)
    route_keys = _assigned_dict_keys(source, "route")

    assert route_keys == {
        "workspace_root",
        "route_features",
        "online_policy",
        "online_execution_decision",
        "workforce_bindings",
    }
    assert route_keys.isdisjoint(
        {
            "execution_topology",
            "lane",
            "model",
            "online_provider",
            "provider",
            "recommended_flow",
            "runtime_selector",
            "target_file",
            "target_files",
        }
    )


def test_daily_cli_exposes_policy_and_evidence_not_route_selectors() -> None:
    source = inspect.getsource(nexus_cli.run.callback)

    for forbidden_option in (
        "--provider",
        "--model",
        "--topology",
        "--route",
        "--runtime",
        "--legacy-runtime",
    ):
        assert forbidden_option not in source
    assert "--online-policy" in source
    assert "--local-assist-policy" in source
    assert "--target-file" in source
    assert "--verify-command" in source


def test_cutover_counts_are_explicit_and_single() -> None:
    fields = canonical_task_seam.CanonicalProductExecutionResult.__dataclass_fields__

    assert fields["production_ingress_count"].default == 1
    assert fields["production_runtime_entry_count"].default == 1
    assert fields["execution_decision_authority"].default == "CapabilityPlanner"
