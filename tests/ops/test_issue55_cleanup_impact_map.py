from pathlib import Path

from scripts.ops.select_tests import load_impact_rules, select_target_details

MISSING_INDEX = Path("/tmp/missing-issue55-impact-index.json")
MISSING_STATS = Path("/tmp/missing-issue55-impact-stats.json")
MISSING_HISTORY = Path("/tmp/missing-issue55-impact-history.jsonl")

DELETED_PATHS = (
    "scripts/brain_b_indexer.py",
    "scripts/core/brain_b_indexer.py",
    "scripts/brain_b_reality_check.py",
    "scripts/core/brain_b_reality_check.py",
    "scripts/reality_check_v2.py",
    "scripts/core/reality_check_v2.py",
    "scripts/trigger_test.py",
    "scripts/core/trigger_test.py",
)


def _details(paths: list[str]):
    return select_target_details(
        paths,
        load_impact_rules(),
        index_path=MISSING_INDEX,
        stats_path=MISSING_STATS,
        history_path=MISSING_HISTORY,
    )


def test_issue55_deleted_experiments_have_exact_high_risk_mappings():
    rules = {rule.code_path: rule for rule in load_impact_rules()}

    for path in DELETED_PATHS:
        assert rules[path].targets == ("tests/ops/test_source_inventory_integrity.py",)
        assert rules[path].risk == "high"
        assert rules[path].risk_reason == "issue55_abandoned_experiment_cleanup_contract"


def test_issue55_deleted_experiments_resolve_without_fallback():
    details = _details(list(DELETED_PATHS))

    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.high_risk_escalated is True
    assert details.risk == "high"
    assert details.risk_reasons == ["issue55_abandoned_experiment_cleanup_contract"]
    assert "tests/ops/test_source_inventory_integrity.py" in details.targets


def test_issue55_unknown_sibling_remains_fail_closed_fallback():
    details = _details(["scripts/brain_b_indexer_v2.py"])

    assert details.unmatched_paths == ["scripts/brain_b_indexer_v2.py"]
    assert details.fallback_used is True
