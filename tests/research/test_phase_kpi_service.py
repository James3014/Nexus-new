import json

from nexus.research.learn.phase_kpi_service import PhaseKPIService
from nexus.research.learn_mode import LearnModeService


def test_phase_kpi_service_returns_empty_metrics_when_no_writeback(tmp_path):
    svc = LearnModeService(tmp_path)
    kpi = PhaseKPIService(svc)
    out = kpi.build_phase_kpi_report(window=50)
    assert out["status"] == "SUCCESS"
    assert out["total_records"] == 0
    assert out["global"]["success_ratio"] == 1.0
    assert out["global"]["required_done_ratio"] == 1.0
    assert set(out["phases"].keys()) == {"P", "X", "D", "R", "A", "C"}


def test_phase_kpi_service_aggregates_phase_and_mode_breakdown(tmp_path):
    svc = LearnModeService(tmp_path)
    svc.phase_writeback_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "phase": "P",
            "phase_status": "SUCCESS",
            "route": {"mode": "light"},
            "writeback_policy": {"required": True},
            "writeback_done": True,
        },
        {
            "phase": "R",
            "phase_status": "PARTIAL",
            "route": {"mode": "research"},
            "writeback_policy": {"required": True},
            "writeback_done": False,
        },
    ]
    svc.phase_writeback_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    kpi = PhaseKPIService(svc)
    out = kpi.build_phase_kpi_report(window=50)
    assert out["total_records"] == 2
    assert out["phases"]["P"]["success_ratio"] == 1.0
    assert out["phases"]["R"]["success_ratio"] == 0.0
    assert out["global"]["required_done_ratio"] == 0.5
    assert out["mode_breakdown"]["light"] == 1
    assert out["mode_breakdown"]["research"] == 1
