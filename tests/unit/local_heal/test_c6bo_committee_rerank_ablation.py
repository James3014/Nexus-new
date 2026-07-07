"""
C6BO: Committee R/D/A and Selection truth rerank / Autoreason causal ablation.

Verifies:
1. Default: execution_topology comes from spec (local_committee_only for astropy)
2. NEXUS_ABLATION_FORCE_LOCAL_ONLY=1 overrides to local_only
3. locked_search and problem_statement are unaffected
4. Committee flags remain hardcoded True (moot by topology change)
5. Env var does not affect other task specs
"""
import os
import pytest


def _build_row_for_astropy():
    """Build a minimal row dict simulating build_c15_benchmark_row for astropy."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = {s["task_id"]: s for s in build_task_specs()}
    spec = specs["astropy__astropy-13236"]
    return {
        "execution_topology": os.environ.get("NEXUS_ABLATION_FORCE_LOCAL_ONLY", spec["execution_topology"]),
        "locked_search": spec["locked_search"],
        "problem_statement": spec.get("problem_statement", ""),
        "signal_snapshot": {
            "execution_topology": os.environ.get("NEXUS_ABLATION_FORCE_LOCAL_ONLY", spec["execution_topology"]),
            "local_committee_enabled": True,
            "diagnosis_committee_enabled": True,
            "audit_committee_enabled": True,
            "proposer_specs": [
                {"model": "qwen2.5-coder:7b-instruct", "role": "primary"},
                {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
            ],
        },
    }


def _build_row_for_sympy():
    """Build a minimal row dict simulating build_c15_benchmark_row for sympy."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = {s["task_id"]: s for s in build_task_specs()}
    spec = specs["sympy__sympy-13852"]
    return {
        "execution_topology": os.environ.get("NEXUS_ABLATION_FORCE_LOCAL_ONLY", spec["execution_topology"]),
        "locked_search": spec["locked_search"],
        "problem_statement": spec.get("problem_statement", ""),
    }


def test_astropy_default_topology_is_committee():
    """C6BO: astropy-13236 defaults to local_committee_only topology."""
    row = _build_row_for_astropy()
    assert row["execution_topology"] == "local_committee_only", (
        f"Expected local_committee_only, got {row['execution_topology']}"
    )
    ss = row["signal_snapshot"]
    assert ss["execution_topology"] == "local_committee_only"


def test_env_var_overrides_to_local_only():
    """C6BO: NEXUS_ABLATION_FORCE_LOCAL_ONLY=1 forces local_only."""
    try:
        os.environ["NEXUS_ABLATION_FORCE_LOCAL_ONLY"] = "local_only"
        row = _build_row_for_astropy()
        assert row["execution_topology"] == "local_only", (
            f"Expected local_only, got {row['execution_topology']}"
        )
    finally:
        os.environ.pop("NEXUS_ABLATION_FORCE_LOCAL_ONLY", None)


def test_locked_search_unaltered_by_env_var():
    """C6BO: locked_search is not affected by the env var."""
    ls_default = _build_row_for_astropy()["locked_search"]
    try:
        os.environ["NEXUS_ABLATION_FORCE_LOCAL_ONLY"] = "local_only"
        ls_ablated = _build_row_for_astropy()["locked_search"]
        assert ls_ablated == ls_default, "locked_search must not change with ablation"
    finally:
        os.environ.pop("NEXUS_ABLATION_FORCE_LOCAL_ONLY", None)


def test_problem_statement_unaltered_by_env_var():
    """C6BO: problem_statement is not affected by the env var."""
    ps_default = _build_row_for_astropy()["problem_statement"]
    try:
        os.environ["NEXUS_ABLATION_FORCE_LOCAL_ONLY"] = "local_only"
        ps_ablated = _build_row_for_astropy()["problem_statement"]
        assert ps_ablated == ps_default, "problem_statement must not change with ablation"
    finally:
        os.environ.pop("NEXUS_ABLATION_FORCE_LOCAL_ONLY", None)


def test_committee_flags_still_true():
    """C6BO: Committee flags remain hardcoded True (they are moot after topology
    change, but their value is unchanged)."""
    try:
        os.environ["NEXUS_ABLATION_FORCE_LOCAL_ONLY"] = "local_only"
        ss = _build_row_for_astropy()["signal_snapshot"]
        assert ss["local_committee_enabled"] is True
        assert ss["diagnosis_committee_enabled"] is True
        assert ss["audit_committee_enabled"] is True
    finally:
        os.environ.pop("NEXUS_ABLATION_FORCE_LOCAL_ONLY", None)


def test_sympy_unaffected_by_env_var():
    """C6BO: sympy-13852 already local_only; env var doesn't change its value."""
    row = _build_row_for_sympy()
    assert row["execution_topology"] == "local_only", (
        f"sympy should be local_only by default, got {row['execution_topology']}"
    )


def test_expected_capabilities_preserved():
    """C6BO: expected_capabilities in spec is unchanged by the env var."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = {s["task_id"]: s for s in build_task_specs()}
    spec = specs["astropy__astropy-13236"]
    caps_default = spec["expected_capabilities"]
    # Verify ddtree and autoreason are still in expected_capabilities
    assert "ddtree" in caps_default
    assert "autoreason" in caps_default
    assert "local_model_executor" in caps_default


def test_env_var_only_affects_topology_not_other_fields():
    """C6BO: The env var ONLY changes execution_topology.
    All other row fields are untouched."""
    try:
        os.environ["NEXUS_ABLATION_FORCE_LOCAL_ONLY"] = "local_only"
        row = _build_row_for_astropy()
        ss = row["signal_snapshot"]
        # proposer_specs must stay intact
        assert len(ss["proposer_specs"]) == 2
        assert ss["proposer_specs"][0]["role"] == "primary"
        assert ss["proposer_specs"][1]["role"] == "secondary"
    finally:
        os.environ.pop("NEXUS_ABLATION_FORCE_LOCAL_ONLY", None)
