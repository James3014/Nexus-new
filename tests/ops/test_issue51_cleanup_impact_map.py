from pathlib import Path

from scripts.ops.select_tests import load_impact_rules, select_target_details

MISSING_INDEX = Path("/tmp/missing-issue204-impact-index.json")
MISSING_STATS = Path("/tmp/missing-issue204-impact-stats.json")
MISSING_HISTORY = Path("/tmp/missing-issue204-impact-history.jsonl")

EXACT_PATHS = (
    "nexus/committee/diversity_sampler.py",
    "nexus/env/diff_report.py",
    "nexus/env/snapshot.py",
    "nexus/policy/compatibility.py",
)


def _details(paths: list[str]):
    return select_target_details(
        paths,
        load_impact_rules(),
        index_path=MISSING_INDEX,
        stats_path=MISSING_STATS,
        history_path=MISSING_HISTORY,
    )


def test_issue51_orphan_cleanup_paths_have_exact_high_risk_rules() -> None:
    rules = load_impact_rules()
    rules_by_path = {rule.code_path: rule for rule in rules}

    expected = {
        "nexus/committee/diversity_sampler.py": (
            "tests/unit/committee",
            "tests/architecture/test_boundaries_v4.py",
        ),
        "nexus/env/diff_report.py": (
            "tests/architecture/test_boundaries_v3.py",
            "tests/architecture/test_boundaries_v4.py",
        ),
        "nexus/env/snapshot.py": (
            "tests/architecture/test_boundaries_v3.py",
            "tests/architecture/test_boundaries_v4.py",
        ),
        "nexus/policy/compatibility.py": (
            "tests/services/test_policy_gate.py",
            "tests/architecture/test_boundaries_v3.py",
            "tests/architecture/test_boundaries_v4.py",
        ),
    }

    for path, targets in expected.items():
        rule = rules_by_path[path]
        assert rule.targets == targets
        assert rule.risk == "high"
        assert rule.risk_reason == "issue51_proven_orphan_cleanup_contract"

    assert "nexus/committee" not in rules_by_path
    assert "nexus/env" not in rules_by_path
    assert "nexus/policy" not in rules_by_path


def test_issue51_orphan_cleanup_paths_resolve_without_fallback() -> None:
    expected_targets = {
        "nexus/committee/diversity_sampler.py": {
            "tests/unit/committee",
            "tests/architecture/test_boundaries_v4.py",
            "tests/services/test_policy_gate.py",
        },
        "nexus/env/diff_report.py": {
            "tests/architecture/test_boundaries_v3.py",
            "tests/architecture/test_boundaries_v4.py",
            "tests/services/test_policy_gate.py",
        },
        "nexus/env/snapshot.py": {
            "tests/architecture/test_boundaries_v3.py",
            "tests/architecture/test_boundaries_v4.py",
            "tests/services/test_policy_gate.py",
        },
        "nexus/policy/compatibility.py": {
            "tests/services/test_policy_gate.py",
            "tests/architecture/test_boundaries_v3.py",
            "tests/architecture/test_boundaries_v4.py",
        },
    }

    for path, targets in expected_targets.items():
        details = _details([path])
        assert set(details.targets) == targets
        assert details.unmatched_paths == []
        assert details.fallback_used is False
        assert details.risk == "high"
        assert details.high_risk_escalated is True
        assert details.risk_reasons == ["issue51_proven_orphan_cleanup_contract"]


def test_issue51_combined_cleanup_paths_are_explicit_and_high_risk() -> None:
    details = _details(list(EXACT_PATHS))

    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.risk == "high"
    assert details.high_risk_escalated is True
    assert details.risk_reasons == ["issue51_proven_orphan_cleanup_contract"]
    assert {
        "tests/unit/committee",
        "tests/architecture/test_boundaries_v3.py",
        "tests/architecture/test_boundaries_v4.py",
        "tests/services/test_policy_gate.py",
    }.issubset(details.targets)


def test_unrelated_unknown_env_path_remains_fail_closed_fallback() -> None:
    details = _details(["nexus/env/new_runtime.py"])

    assert details.fallback_used is True
    assert details.unmatched_paths == ["nexus/env/new_runtime.py"]
