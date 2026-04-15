import pytest
from nexus.research.reporting.report_schema import UnifiedAggregateReport

def test_unified_report_to_dict():
    report = UnifiedAggregateReport(
        mode="hyper",
        success_rate=0.8,
        total_cases=10
    )
    d = report.to_dict()
    assert d["mode"] == "hyper"
    assert d["success_rate"] == 0.8
    assert "timestamp" in d
