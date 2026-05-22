from dataclasses import replace

from scripts.ops.zero_trust_v2_report_dag import build_report_dag, build_report_manifest, topological_report_order


def test_zero_trust_v2_report_dag_orders_receipt_import_before_runtime_apply():
    dag = build_report_dag()
    order = topological_report_order(dag)

    assert order.index("m45_m52_completion") < order.index("behavior_evidence")
    assert order.index("behavior_evidence") < order.index("behavior_promotion_report")
    assert order.index("behavior_promotion_report") < order.index("manual_trial")
    assert order.index("manual_trial") < order.index("p0_rollout")
    assert order.index("p0_rollout") < order.index("runtime_apply")
    assert order.index("runtime_apply") < order.index("unified_mainline")
    assert dag["runtime_apply"].public_benchmark_allowed is False


def test_zero_trust_v2_report_dag_rejects_unknown_dependency():
    dag = build_report_dag()
    dag["runtime_apply"] = replace(dag["runtime_apply"], depends_on=("missing_report",))

    try:
        topological_report_order(dag)
    except ValueError as exc:
        assert "unknown dependency" in str(exc)
        assert "missing_report" in str(exc)
    else:
        raise AssertionError("expected missing dependency to fail closed")


def test_zero_trust_v2_report_manifest_exposes_order_and_claim_boundaries():
    manifest = build_report_manifest(build_report_dag())

    assert manifest["schema"] == "nexus_zero_trust_v2_report_dag_manifest_v1"
    assert manifest["order"].index("m45_m52_completion") < manifest["order"].index("runtime_apply")
    assert manifest["runtime_update_allowed_nodes"] == ["runtime_apply"]
    assert manifest["public_benchmark_allowed_nodes"] == []
    assert manifest["nodes"]["runtime_apply"]["runtime_update_allowed"] is True
    assert manifest["nodes"]["public_claim_gate_review"]["public_benchmark_allowed"] is False
