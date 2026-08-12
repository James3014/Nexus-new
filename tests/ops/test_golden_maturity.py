from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/ops/check_golden_maturity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_golden_maturity", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(
    execution: str = "passed",
    *,
    collection: str = "collected",
    status: str = "covered",
    corpus: str = "a" * 64,
    revision: str = "1" * 40,
) -> dict[str, object]:
    return {
        "schema": "nexus.golden_behavior_eval.v1",
        "source_revision": revision,
        "source_tree": "2" * 40,
        "workspace_dirty": False,
        "corpus_identity": corpus,
        "evaluator_identity": "b" * 64,
        "dependency_lock_identity": "c" * 64,
        "case_count": 50,
        "selected_case_count": 1,
        "test_bound_case_count": 1,
        "probe_bound_case_count": 0,
        "default_automated_case_count": 1 if status == "covered" else 0,
        "finding_case_count": 1 if status == "finding" else 0,
        "findings_included_in_eval": False,
        "test_node_count": 1 if status == "covered" else 0,
        "collection_node_count": 1,
        "collection_exit_code": 0 if collection == "collected" else 4,
        "pytest_exit_code": 0 if execution == "passed" else 1,
        "validation_errors": [],
        "case_evidence": [
            {
                "case_id": "GB-001",
                "status": status,
                "finding_probe": None,
                "witnesses": [
                    {
                        "nodeid": "tests/test_example.py::test_behavior",
                        "collection_status": collection,
                        "collection_exit_code": 0 if collection == "collected" else 4,
                        "execution_status": execution,
                    }
                ],
            }
        ],
        "findings": {},
    }


def test_three_consecutive_clean_reports_are_stable() -> None:
    module = _load_module()
    result = module.project_maturity([_report()] * 3)

    assert result["status"] == "PASS"
    assert result["cases"] == [
        {
            "case_id": "GB-001",
            "golden_status": "covered",
            "maturity": "STABLE",
            "consecutive_clean_runs": 3,
            "required_clean_runs": 3,
            "witnesses": ["tests/test_example.py::test_behavior"],
        }
    ]


@pytest.mark.parametrize("count", [1, 2])
def test_fewer_than_three_clean_reports_remain_candidate(count: int) -> None:
    module = _load_module()
    result = module.project_maturity([_report()] * count)

    assert result["cases"][0]["maturity"] == "CANDIDATE"
    assert result["cases"][0]["consecutive_clean_runs"] == count


@pytest.mark.parametrize(
    ("reports", "expected"),
    [
        ([_report(), _report("failed")], "FLAKY"),
        ([_report("failed")], "DETERMINISTIC_FAILURE"),
        ([_report("execution_unattributed")], "INFRA_FAILURE"),
        ([_report(collection="collection_failed")], "COLLECTION_DRIFT"),
        ([_report(), _report(corpus="d" * 64)], "REQUALIFY"),
        ([_report(), _report(revision="3" * 40)], "REQUALIFY"),
    ],
)
def test_negative_outcomes_remain_distinct(reports: list[dict[str, object]], expected: str) -> None:
    module = _load_module()
    result = module.project_maturity(reports)

    assert result["cases"][0]["maturity"] == expected


def test_findings_are_never_promoted_or_counted_clean() -> None:
    module = _load_module()
    report = _report("not_executed_finding_excluded", status="finding")
    report["findings"] = {"GBF-001": "known gap"}
    report["case_evidence"][0]["finding_probe"] = "probe"  # type: ignore[index]
    result = module.project_maturity([report] * 3)

    assert result["cases"][0]["golden_status"] == "finding"
    assert result["cases"][0]["maturity"] == "FINDING"


@pytest.mark.parametrize(
    "execution",
    ["skipped", "not_executed_validate_only", "not_executed_validation_failed"],
)
def test_nonexecuted_or_skipped_witnesses_are_infrastructure_failures(
    execution: str,
) -> None:
    module = _load_module()

    result = module.project_maturity([_report(execution)])

    assert result["cases"][0]["maturity"] == "INFRA_FAILURE"


def test_nonzero_pytest_exit_cannot_be_hidden_by_passing_witnesses() -> None:
    module = _load_module()
    report = _report()
    report["pytest_exit_code"] = 3

    result = module.project_maturity([report])

    assert result["cases"][0]["maturity"] == "INFRA_FAILURE"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report.update(schema="wrong"),
        lambda report: report.update(corpus_identity="bad"),
        lambda report: report.update(validation_errors=["bad"]),
        lambda report: report.update(selected_case_count=2),
        lambda report: report.update(test_node_count=2),
        lambda report: report.update(findings_included_in_eval="false"),
        lambda report: report.update(collection_exit_code=False),
        lambda report: report["case_evidence"].append(report["case_evidence"][0]),
        lambda report: report["case_evidence"][0]["witnesses"].append(
            report["case_evidence"][0]["witnesses"][0]
        ),
    ],
)
def test_malformed_or_contradictory_reports_fail_closed(mutate) -> None:
    module = _load_module()
    report = _report()
    mutate(report)

    result = module.project_maturity([report])

    assert result["status"] == "FAIL_CLOSED"
    assert result["failures"]


def test_cli_rejects_duplicate_json_keys_and_output_is_deterministic(tmp_path: Path) -> None:
    module = _load_module()
    history = tmp_path / "history.json"
    history.write_text(
        '{"reports": [], "reports": []}',
        encoding="utf-8",
    )
    assert module.main(["--history", str(history)]) == 2

    payload = {"reports": [_report(), _report(), _report()]}
    history.write_text(json.dumps(payload), encoding="utf-8")
    first = module.render_projection(module.load_and_project(history))
    second = module.render_projection(module.load_and_project(history))
    assert first == second
