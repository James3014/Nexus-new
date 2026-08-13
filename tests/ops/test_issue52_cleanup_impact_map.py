from pathlib import Path

from scripts.ops.select_tests import load_impact_rules, select_target_details

MISSING_INDEX = Path("/tmp/missing-issue52-impact-index.json")
MISSING_STATS = Path("/tmp/missing-issue52-impact-stats.json")
MISSING_HISTORY = Path("/tmp/missing-issue52-impact-history.jsonl")

EXPECTED = {
    "scripts/legacy/git_manager.py": ("tests/services/test_git_service.py",),
    "scripts/legacy/linter.py": ("tests/services/test_linter.py",),
    "scripts/legacy/llm_client.py": (
        "tests/test_battlesuit_gateway.py",
        "tests/test_llm_token_regex.py",
    ),
    "scripts/legacy/patcher.py": ("tests/services/test_patcher.py",),
    "scripts/legacy/reporter.py": ("tests/test_reporter.py",),
    "scripts/legacy/workspace_manager.py": (
        "tests/services/test_workspace_manager.py",
        "tests/benchmark/test_workspace.py",
    ),
}


def _details(paths: list[str]):
    return select_target_details(
        paths,
        load_impact_rules(),
        index_path=MISSING_INDEX,
        stats_path=MISSING_STATS,
        history_path=MISSING_HISTORY,
    )


def test_issue52_deleted_adapters_have_exact_high_risk_mappings():
    rules_by_path = {rule.code_path: rule for rule in load_impact_rules()}

    for path, targets in EXPECTED.items():
        rule = rules_by_path[path]
        assert rule.targets == targets
        assert rule.risk == "high"
        assert rule.risk_reason == "issue52_archived_adapter_cleanup_contract"


def test_issue52_deleted_adapters_resolve_without_fallback():
    details = _details(list(EXPECTED))

    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.high_risk_escalated is True
    assert details.risk == "high"
    assert details.risk_reasons == ["issue52_archived_adapter_cleanup_contract"]
    assert set(details.targets) == {
        target for targets in EXPECTED.values() for target in targets
    } | {"tests/services/test_policy_gate.py"}


def test_issue52_unknown_legacy_sibling_remains_fail_closed_fallback():
    details = _details(["scripts/legacy/new_adapter.py"])

    assert details.unmatched_paths == ["scripts/legacy/new_adapter.py"]
    assert details.fallback_used is True
